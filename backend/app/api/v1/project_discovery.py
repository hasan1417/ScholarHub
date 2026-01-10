"""REST endpoints for project-level discovery preferences and results."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.core.config import settings
from app.database import get_db
from app.models import (
    ProjectRole,
    ProjectReference,
    ProjectReferenceStatus,
    ProjectReferenceOrigin,
    ProjectDiscoveryResultStatus,
    ProjectDiscoveryRunType,
    ProjectDiscoveryResult as ProjectDiscoveryResultModel,
    ProjectDiscoveryRun,
    User,
)
from app.schemas.project import (
    ProjectDiscoveryPreferences,
    ProjectDiscoveryPreferencesUpdate,
)
from urllib.parse import urlparse

from app.services.paper_discovery.models import PaperSource
from app.services.reference_ingestion_service import ingest_reference_pdf
from app.services.project_discovery_service import ProjectDiscoveryManager
from app.services.activity_feed import record_project_activity, preview_text


logger = logging.getLogger(__name__)


router = APIRouter()


OPENALEX_PDF_BLOCKLIST = (
    'nature.com',
    'www.nature.com',
    'rdcu.be',
    'doi.org',
    'cell.com',
    'www.cell.com',
    'linkinghub.elsevier.com',
    'sciencedirect.com',
    'www.sciencedirect.com',
)


def _null_if_blocked_openalex_pdf(source: str, url: str | None) -> str | None:
    if not url or source != PaperSource.OPENALEX.value:
        return url
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return None
    if any(host == blocked or host.endswith(blocked) for blocked in OPENALEX_PDF_BLOCKLIST):
        return None
    return url


def _guard_feature() -> None:
    """Ensure the discovery feature flag is enabled."""
    if not settings.PROJECT_REFERENCE_SUGGESTIONS_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project discovery disabled",
        )


def _ensure_discovery_schema(db: Session) -> None:
    """Validate that discovery tables exist before serving requests."""
    inspector = inspect(db.get_bind())
    required_tables = ("project_discovery_runs", "project_discovery_results")
    missing = [table for table in required_tables if not inspector.has_table(table)]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Project discovery storage is unavailable. Run the latest database "
                "migrations before using this feature."
            ),
        )


def _serialize_result(
    result_row: ProjectDiscoveryResultModel,
    run: ProjectDiscoveryRun,
) -> DiscoveryResultItem:
    """Convert ORM rows into API-facing discovery result items."""
    payload = result_row.payload or {}
    reference = result_row.reference

    pdf_url = _null_if_blocked_openalex_pdf(result_row.source, payload.get('pdf_url'))
    open_access_url = _null_if_blocked_openalex_pdf(result_row.source, payload.get('open_access_url'))
    is_open_access = payload.get('is_open_access')
    has_pdf = payload.get('has_pdf')

    if not pdf_url:
        has_pdf = False
        is_open_access = False
    else:
        has_pdf = True if has_pdf is None else bool(has_pdf)
        is_open_access = bool(is_open_access)

    reference_pdf = None
    if reference:
        reference_pdf = reference.pdf_url
        reference_pdf = _null_if_blocked_openalex_pdf(result_row.source, reference_pdf)
        if pdf_url is None and reference_pdf:
            pdf_url = reference_pdf
        if open_access_url is None and reference.url and reference.is_open_access:
            open_access_url = reference.url
        if is_open_access is None:
            is_open_access = bool(reference.is_open_access)
    if has_pdf is None:
        has_pdf = bool(pdf_url)

    # Prefer explicit source_url from payload; fall back to reference.url or DOI resolver
    source_url = payload.get('source_url')
    if not source_url and reference and reference.url:
        source_url = reference.url
    if not source_url and result_row.doi:
        source_url = f"https://doi.org/{result_row.doi}"

    return DiscoveryResultItem(
        id=result_row.id,
        run_id=result_row.run_id,
        run_type=run.run_type,
        status=result_row.status,
        source=result_row.source,
        doi=result_row.doi,
        title=result_row.title,
        summary=result_row.summary,
        authors=result_row.authors,
        published_year=result_row.published_year,
        relevance_score=result_row.relevance_score,
        created_at=result_row.created_at,
        promoted_at=result_row.promoted_at,
        dismissed_at=result_row.dismissed_at,
        run_started_at=run.started_at,
        run_completed_at=run.completed_at,
        is_open_access=is_open_access,
        has_pdf=has_pdf,
        pdf_url=pdf_url,
        open_access_url=open_access_url,
        source_url=source_url,
    )


class DiscoveryRunRequest(ProjectDiscoveryPreferencesUpdate):
    """Payload used when manually triggering a discovery run."""

    max_results: int | None = None


class DiscoveryRunResponse(BaseModel):
    """Summary response describing a completed discovery run."""

    run_id: UUID
    total_found: int
    results_created: int
    references_created: int
    project_suggestions_created: int
    last_run_at: datetime


class DiscoveryResultItem(BaseModel):
    """Serialized representation of a single discovery result."""

    id: UUID
    run_id: UUID
    run_type: ProjectDiscoveryRunType
    status: ProjectDiscoveryResultStatus
    source: str
    doi: str | None
    title: str | None
    summary: str | None
    authors: list[str] | None
    published_year: int | None
    relevance_score: float | None
    created_at: datetime
    promoted_at: datetime | None
    dismissed_at: datetime | None
    run_started_at: datetime
    run_completed_at: datetime | None
    is_open_access: bool | None = None
    has_pdf: bool | None = None
    pdf_url: str | None = None
    open_access_url: str | None = None
    source_url: str | None = None

    class Config:  # pylint: disable=too-few-public-methods
        """Pydantic configuration for ORM compatibility."""

        from_attributes = True


class DiscoveryResultsResponse(BaseModel):
    """Paginated wrapper returned when listing discovery results."""

    total: int
    results: list[DiscoveryResultItem]


class DiscoveryCountResponse(BaseModel):
    """Lightweight counter used by the badge in the UI."""

    pending: int


class DiscoveryClearResponse(BaseModel):
    """Simple payload returned when clearing dismissed discovery results."""

    cleared: int


@router.get("/projects/{project_id}/discovery/settings", response_model=ProjectDiscoveryPreferences)
def get_discovery_settings(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return stored discovery preferences for a project."""
    _guard_feature()
    _ensure_discovery_schema(db)
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    manager = ProjectDiscoveryManager(db)
    return manager.as_preferences(project.discovery_preferences)


@router.put("/projects/{project_id}/discovery/settings", response_model=ProjectDiscoveryPreferences)
def update_discovery_settings(
    project_id: UUID,
    payload: ProjectDiscoveryPreferencesUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Persist updates to discovery preferences (admin/editor only)."""
    _guard_feature()
    _ensure_discovery_schema(db)
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    manager = ProjectDiscoveryManager(db)
    current_preferences = manager.as_preferences(
        project.discovery_preferences
    ).model_dump(mode="json")
    merged = manager.merge_preferences(current_preferences, payload)
    project.discovery_preferences = merged
    db.commit()
    db.refresh(project)
    return manager.as_preferences(project.discovery_preferences)


@router.post("/projects/{project_id}/discovery/run", response_model=DiscoveryRunResponse)
def run_project_discovery(
    project_id: UUID,
    payload: DiscoveryRunRequest = DiscoveryRunRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a manual discovery run for the given project."""
    try:
        logger.info(
            "Project %s run discovery payload: query=%s keywords=%s sources=%s max_results=%s auto_refresh=%s refresh_interval=%s",
            project_id,
            getattr(payload, 'query', None),
            getattr(payload, 'keywords', None),
            getattr(payload, 'sources', None),
            getattr(payload, 'max_results', None),
            getattr(payload, 'auto_refresh_enabled', None),
            getattr(payload, 'refresh_interval_hours', None),
        )
    except Exception:
        pass
    _guard_feature()
    _ensure_discovery_schema(db)
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    manager = ProjectDiscoveryManager(db)
    stored_preferences = manager.as_preferences(project.discovery_preferences)
    effective_preferences = ProjectDiscoveryPreferences.model_validate(
        stored_preferences.model_dump(mode="json")
    )
    override_query = payload.query
    if payload.keywords is not None:
        effective_preferences.keywords = payload.keywords
    if payload.sources is not None:
        effective_preferences.sources = payload.sources
    if payload.auto_refresh_enabled is not None:
        effective_preferences.auto_refresh_enabled = payload.auto_refresh_enabled
    if payload.refresh_interval_hours is not None:
        effective_preferences.refresh_interval_hours = payload.refresh_interval_hours

    # Manual overrides should replace stored limits entirely; leave None when not provided.
    effective_preferences.max_results = payload.max_results
    effective_preferences.relevance_threshold = payload.relevance_threshold

    try:
        result = manager.discover(
            project,
            current_user,
            effective_preferences,
            override_query=override_query,
            max_results=payload.max_results or 20,
            run_type=ProjectDiscoveryRunType.MANUAL,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:
        # Log the full error for debugging but return a user-friendly message
        logger.error("Discovery error for project %s: %s", project_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Discovery search failed due to external service issues. Please try again later."
        ) from exc

    updated_preferences = manager.as_preferences(project.discovery_preferences)

    restored_preferences = stored_preferences.model_dump(mode="json")
    if updated_preferences.last_run_at is not None:
        restored_preferences['last_run_at'] = updated_preferences.last_run_at.isoformat()
    else:
        restored_preferences.pop('last_run_at', None)
    restored_preferences['last_result_count'] = updated_preferences.last_result_count
    restored_preferences['last_status'] = updated_preferences.last_status
    project.discovery_preferences = restored_preferences
    db.commit()
    db.refresh(project)

    last_run = updated_preferences.last_run_at
    if isinstance(last_run, str):
        last_run_dt = datetime.fromisoformat(last_run)
    else:
        last_run_dt = last_run or datetime.now(timezone.utc)

    run_id = result.run_id or manager.last_run_id
    return DiscoveryRunResponse(
        run_id=run_id,
        total_found=result.total_found,
        results_created=result.results_created,
        references_created=result.references_created,
        project_suggestions_created=result.project_suggestions_created,
        last_run_at=last_run_dt,
    )


@router.get("/projects/{project_id}/discovery/results", response_model=DiscoveryResultsResponse)
def list_discovery_results(  # pylint: disable=too-many-arguments,too-many-locals,too-many-positional-arguments
    project_id: UUID,
    status_filter: ProjectDiscoveryResultStatus | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List discovery results for a project with optional status filtering."""
    _guard_feature()
    _ensure_discovery_schema(db)
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    base_query = (
        db.query(ProjectDiscoveryResultModel, ProjectDiscoveryRun)
        .join(ProjectDiscoveryRun, ProjectDiscoveryResultModel.run_id == ProjectDiscoveryRun.id)
        .filter(ProjectDiscoveryResultModel.project_id == project_id)
    )

    if status_filter is not None:
        base_query = base_query.filter(ProjectDiscoveryResultModel.status == status_filter)

    total = base_query.count()

    rows = (
        base_query
        .order_by(ProjectDiscoveryResultModel.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items: list[DiscoveryResultItem] = [
        _serialize_result(result_row, run)
        for result_row, run in rows
    ]

    return DiscoveryResultsResponse(total=total, results=items)


@router.get(
    "/projects/{project_id}/discovery/results/pending/count",
    response_model=DiscoveryCountResponse,
)
def get_pending_discovery_count(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return the number of pending discovery results for badge display."""
    _guard_feature()
    _ensure_discovery_schema(db)
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    pending = (
        db.query(ProjectDiscoveryResultModel)
        .filter(
            ProjectDiscoveryResultModel.project_id == project_id,
            ProjectDiscoveryResultModel.status == ProjectDiscoveryResultStatus.PENDING,
        )
        .count()
    )

    return DiscoveryCountResponse(pending=pending)


@router.post(
    "/projects/{project_id}/discovery/results/{result_id}/promote",
    response_model=DiscoveryResultItem,
)
def promote_discovery_result(
    project_id: UUID,
    result_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):  # pylint: disable=too-many-arguments,too-many-positional-arguments
    """Promote a discovery result into an approved project reference."""
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    row = (
        db.query(ProjectDiscoveryResultModel, ProjectDiscoveryRun)
        .join(ProjectDiscoveryRun, ProjectDiscoveryResultModel.run_id == ProjectDiscoveryRun.id)
        .filter(
            ProjectDiscoveryResultModel.project_id == project_id,
            ProjectDiscoveryResultModel.id == result_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

    result_row, run = row
    if result_row.status == ProjectDiscoveryResultStatus.DISMISSED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Result was dismissed")

    project_ref = None
    if result_row.reference_id:
        project_ref = (
            db.query(ProjectReference)
            .filter(
                ProjectReference.project_id == project_id,
                ProjectReference.reference_id == result_row.reference_id,
            )
            .first()
        )

    created_project_reference = False
    if project_ref is None:
        if not result_row.reference_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Result not linked to a reference",
            )
        project_ref = ProjectReference(
            project_id=project_id,
            reference_id=result_row.reference_id,
            status=ProjectReferenceStatus.PENDING,
            origin=(
                ProjectReferenceOrigin.AUTO_DISCOVERY
                if run.run_type == ProjectDiscoveryRunType.AUTO
                else ProjectReferenceOrigin.MANUAL_DISCOVERY
            ),
            discovery_run_id=run.id,
        )
        db.add(project_ref)
        created_project_reference = True

    project_ref.status = ProjectReferenceStatus.APPROVED
    project_ref.decided_by = current_user.id
    project_ref.decided_at = datetime.now(timezone.utc)
    if not project_ref.discovery_run_id:
        project_ref.discovery_run_id = run.id
    if project_ref.origin == ProjectReferenceOrigin.UNKNOWN:
        project_ref.origin = (
            ProjectReferenceOrigin.AUTO_DISCOVERY
            if run.run_type == ProjectDiscoveryRunType.AUTO
            else ProjectReferenceOrigin.MANUAL_DISCOVERY
        )

    result_row.status = ProjectDiscoveryResultStatus.PROMOTED
    result_row.promoted_at = datetime.now(timezone.utc)
    result_row.dismissed_at = None

    db.flush()

    reference = project_ref.reference
    record_project_activity(
        db=db,
        project=project,
        actor=current_user,
        event_type="project-reference.approved",
        payload={
            "category": "project-reference",
            "action": "approved",
            "source": "discovery-promote",
            "project_reference_id": str(project_ref.id),
            "reference_id": str(project_ref.reference_id),
            "reference_title": preview_text(reference.title if reference else None, 160),
            "discovery_run_id": str(run.id),
            "discovery_result_id": str(result_row.id),
            "origin": project_ref.origin.value if hasattr(project_ref.origin, 'value') else project_ref.origin,
            "created_via_promote": created_project_reference,
        },
    )

    db.commit()

    reference = project_ref.reference
    if reference and reference.pdf_url and not reference.document_id:
        try:
            owner_override = str(current_user.id) if current_user and current_user.id else None
            if ingest_reference_pdf(db, reference, owner_id=owner_override):
                db.refresh(reference)
        except Exception as exc:  # pragma: no cover - ingestion best effort
            logger.warning(
                "Failed to ingest PDF during discovery promotion for reference %s: %s",
                reference.id if reference else 'unknown',
                exc,
            )

    db.refresh(result_row)
    db.refresh(run)

    return _serialize_result(result_row, run)


@router.post(
    "/projects/{project_id}/discovery/results/{result_id}/dismiss",
    response_model=DiscoveryResultItem,
)
def dismiss_discovery_result(
    project_id: UUID,
    result_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):  # pylint: disable=too-many-arguments
    """Dismiss a discovery result and mark any linked reference as rejected."""
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    row = (
        db.query(ProjectDiscoveryResultModel, ProjectDiscoveryRun)
        .join(ProjectDiscoveryRun, ProjectDiscoveryResultModel.run_id == ProjectDiscoveryRun.id)
        .filter(
            ProjectDiscoveryResultModel.project_id == project_id,
            ProjectDiscoveryResultModel.id == result_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Result not found",
        )

    result_row, run = row
    if result_row.status == ProjectDiscoveryResultStatus.PROMOTED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Result already promoted",
        )

    project_ref = None
    if result_row.reference_id:
        project_ref = (
            db.query(ProjectReference)
            .filter(
                ProjectReference.project_id == project_id,
                ProjectReference.reference_id == result_row.reference_id,
            )
            .first()
        )

    if project_ref:
        project_ref.status = ProjectReferenceStatus.REJECTED
        project_ref.decided_by = current_user.id
        project_ref.decided_at = datetime.now(timezone.utc)
        if not project_ref.discovery_run_id:
            project_ref.discovery_run_id = run.id
        if project_ref.origin == ProjectReferenceOrigin.UNKNOWN:
            project_ref.origin = (
                ProjectReferenceOrigin.AUTO_DISCOVERY
                if run.run_type == ProjectDiscoveryRunType.AUTO
                else ProjectReferenceOrigin.MANUAL_DISCOVERY
            )

    result_row.status = ProjectDiscoveryResultStatus.DISMISSED
    result_row.dismissed_at = datetime.now(timezone.utc)

    db.flush()

    db.commit()
    db.refresh(result_row)
    db.refresh(run)

    return _serialize_result(result_row, run)


@router.delete(
    "/projects/{project_id}/discovery/results/{result_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_discovery_result(
    project_id: UUID,
    result_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a manual discovery result and any pending project reference it created."""
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    row = (
        db.query(ProjectDiscoveryResultModel, ProjectDiscoveryRun)
        .join(ProjectDiscoveryRun, ProjectDiscoveryResultModel.run_id == ProjectDiscoveryRun.id)
        .filter(
            ProjectDiscoveryResultModel.project_id == project_id,
            ProjectDiscoveryResultModel.id == result_id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")

    result_row, run = row
    if run.run_type != ProjectDiscoveryRunType.MANUAL:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only manual discovery results can be deleted")
    if result_row.status == ProjectDiscoveryResultStatus.PROMOTED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Promoted results cannot be deleted")

    project_ref = None
    if result_row.reference_id:
        project_ref = (
            db.query(ProjectReference)
            .filter(
                ProjectReference.project_id == project_id,
                ProjectReference.reference_id == result_row.reference_id,
            )
            .first()
        )

    if project_ref and project_ref.status == ProjectReferenceStatus.PENDING:
        db.delete(project_ref)

    db.delete(result_row)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/projects/{project_id}/discovery/results/dismissed",
    response_model=DiscoveryClearResponse,
)
def clear_dismissed_discovery_results(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove all dismissed discovery results for a project."""
    _guard_feature()
    _ensure_discovery_schema(db)
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    query = (
        db.query(ProjectDiscoveryResultModel)
        .filter(
            ProjectDiscoveryResultModel.project_id == project_id,
            ProjectDiscoveryResultModel.status == ProjectDiscoveryResultStatus.DISMISSED,
        )
    )

    cleared = query.count()
    if cleared == 0:
        return DiscoveryClearResponse(cleared=0)

    query.delete(synchronize_session=False)
    db.commit()
    return DiscoveryClearResponse(cleared=cleared)
