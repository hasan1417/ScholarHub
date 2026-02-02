from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.core.config import settings
from app.database import get_db
from app.models import (
    PaperReference,
    ProjectReference,
    ProjectReferenceStatus,
    ProjectRole,
    ProjectDiscoveryRunType,
    Reference,
    ResearchPaper,
    User,
)
from app.models.document import DocumentStatus
from app.services.project_reference_service import ProjectReferenceSuggestionService
from app.services.project_discovery_service import ProjectDiscoveryManager
from app.services.activity_feed import record_project_activity, preview_text
from app.services.embedding_worker import queue_library_paper_embedding_sync
from pydantic import BaseModel


router = APIRouter()


def _guard_feature() -> None:
    if not settings.PROJECT_REFERENCE_SUGGESTIONS_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project references feature disabled")


class ProjectReferenceResponse(dict):
    """Lightweight serializer to avoid creating a dedicated Pydantic model right now."""


class AttachReferencePayload(BaseModel):
    paper_id: UUID


def _is_valid_uuid(val: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


def _parse_short_id(url_id: str) -> Optional[str]:
    """Extract short_id from a URL identifier (slug-shortid or just shortid)."""
    if not url_id or _is_valid_uuid(url_id):
        return None
    if len(url_id) == 8 and url_id.isalnum():
        return url_id
    last_hyphen = url_id.rfind('-')
    if last_hyphen > 0:
        potential_short_id = url_id[last_hyphen + 1:]
        if len(potential_short_id) == 8 and potential_short_id.isalnum():
            return potential_short_id
    return None


def _coerce_document_status(value) -> DocumentStatus | None:
    if isinstance(value, DocumentStatus):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        try:
            return DocumentStatus(value)
        except ValueError:
            try:
                return DocumentStatus(value.lower())
            except ValueError:
                return None
    return None


def _sync_reference_analysis_state(ref: Reference) -> bool:
    if not ref:
        return False

    changed = False
    document = ref.document

    if document is not None:
        doc_status = _coerce_document_status(getattr(document, "status", None))
        processed_for_ai = bool(getattr(document, "is_processed_for_ai", False))

        if doc_status == DocumentStatus.PROCESSED and processed_for_ai:
            if ref.status != 'analyzed':
                ref.status = 'analyzed'
                changed = True
        elif doc_status in {DocumentStatus.PROCESSING, DocumentStatus.UPLOADING}:
            if ref.status == 'pending':
                ref.status = 'ingested'
                changed = True
        elif doc_status == DocumentStatus.PROCESSED and not processed_for_ai:
            if ref.status == 'pending':
                ref.status = 'ingested'
                changed = True

    return changed


def _serialize_project_reference(pr: ProjectReference) -> ProjectReferenceResponse:
    ref = pr.reference
    document = ref.document if ref else None

    document_id = str(document.id) if document else None
    document_status = None
    document_download_url = None
    pdf_processed = False

    if document:
        status_attr = getattr(document.status, "value", None)
        document_status = status_attr or str(document.status)
        document_download_url = f"/api/v1/documents/{document.id}/download"
        pdf_processed = bool(getattr(document, "is_processed_for_ai", False))

    related_papers = []
    if ref:
        for link in ref.paper_links:
            paper = link.paper
            if paper and paper.project_id == pr.project_id:
                related_papers.append(
                    {
                        "paper_id": str(link.paper_id),
                        "title": paper.title,
                    }
                )

    return ProjectReferenceResponse(
        id=str(pr.id),
        reference_id=str(pr.reference_id),
        project_id=str(pr.project_id),
        status=pr.status.value,
        confidence=pr.confidence,
        decided_by=str(pr.decided_by) if pr.decided_by else None,
        decided_at=pr.decided_at.isoformat() if pr.decided_at else None,
        created_at=pr.created_at.isoformat() if pr.created_at else None,
        updated_at=pr.updated_at.isoformat() if pr.updated_at else None,
        reference={
            "id": str(ref.id) if ref else None,
            "title": ref.title if ref else None,
            "authors": ref.authors if ref else None,
            "year": ref.year if ref else None,
            "doi": ref.doi if ref else None,
            "url": ref.url if ref else None,
            "source": ref.source if ref else None,
            "journal": ref.journal if ref else None,
            "abstract": ref.abstract if ref else None,
            "summary": ref.summary if ref else None,
            "status": ref.status if ref else None,
            "is_open_access": ref.is_open_access if ref else None,
            "pdf_url": ref.pdf_url if ref else None,
            "pdf_processed": pdf_processed,
            "document_id": document_id,
            "document_status": document_status,
            "document_download_url": document_download_url,
        } if ref else None,
        papers=related_papers,
    )


@router.get("/projects/{project_id}/references/suggestions")
def list_reference_suggestions(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    suggestions = (
        db.query(ProjectReference)
        .filter(
            ProjectReference.project_id == project.id,
            ProjectReference.status == ProjectReferenceStatus.PENDING,
        )
        .order_by(ProjectReference.created_at.desc())
        .all()
    )

    dirty = False
    for item in suggestions:
        if _sync_reference_analysis_state(item.reference):
            dirty = True

    if dirty:
        db.commit()

    return {
        "project_id": str(project.id),
        "suggestions": [_serialize_project_reference(item) for item in suggestions],
    }


@router.get("/projects/{project_id}/references")
def list_project_references(
    project_id: str,
    status_filter: ProjectReferenceStatus | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    query = db.query(ProjectReference).filter(ProjectReference.project_id == project.id)
    if status_filter is not None:
        query = query.filter(ProjectReference.status == status_filter)

    references = query.order_by(ProjectReference.created_at.desc()).all()

    dirty = False
    for item in references:
        if _sync_reference_analysis_state(item.reference):
            dirty = True

    if dirty:
        db.commit()

    return {
        "project_id": str(project.id),
        "references": [_serialize_project_reference(item) for item in references],
    }


@router.post("/projects/{project_id}/references/suggestions/refresh")
def refresh_reference_suggestions(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    discovery_summary = None
    preferences = (project.discovery_preferences or {})
    if preferences.get('auto_refresh_enabled'):
        manager = ProjectDiscoveryManager(db)
        prefs_model = manager.as_preferences(preferences)
        try:
            discovery_result = manager.discover(
                project,
                current_user,
                prefs_model,
                run_type=ProjectDiscoveryRunType.AUTO,
            )
            discovery_summary = discovery_result.__dict__
        except Exception as exc:  # pragma: no cover - discovery failures are non-fatal
            logger = logging.getLogger(__name__)
            logger.warning("Auto discovery failed: %s", exc)

    service = ProjectReferenceSuggestionService(db)
    created, skipped = service.generate_suggestions(project, actor=current_user)
    return {
        "project_id": str(project.id),
        "created": created,
        "skipped": skipped,
        "discovery": discovery_summary,
    }


@router.post("/projects/{project_id}/references/suggestions", status_code=status.HTTP_201_CREATED)
def create_reference_suggestion(
    project_id: str,
    reference_id: UUID,
    confidence: Optional[float] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    reference = db.query(Reference).filter(Reference.id == reference_id).first()
    if not reference:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")

    existing = (
        db.query(ProjectReference)
        .filter(
            ProjectReference.project_id == project.id,
            ProjectReference.reference_id == reference_id,
        )
        .first()
    )
    if existing:
        return {
            "id": str(existing.id),
            "status": existing.status.value,
        }

    suggestion = ProjectReference(
        project_id=project.id,
        reference_id=reference_id,
        status=ProjectReferenceStatus.PENDING,
        confidence=confidence,
    )
    db.add(suggestion)
    db.commit()
    db.refresh(suggestion)

    return {
        "id": str(suggestion.id),
        "status": suggestion.status.value,
    }


def _update_reference_status(
    project_id: str,
    project_reference_id: UUID,
    new_status: ProjectReferenceStatus,
    *,
    db: Session,
    current_user: User,
    paper_id: Optional[UUID] = None,
) -> ProjectReference:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    project_ref = (
        db.query(ProjectReference)
        .filter(
            ProjectReference.id == project_reference_id,
            ProjectReference.project_id == project.id,
        )
        .first()
    )
    if not project_ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project reference not found")

    previous_status = project_ref.status
    project_ref.status = new_status
    project_ref.decided_by = current_user.id
    project_ref.decided_at = None if new_status == ProjectReferenceStatus.PENDING else project_ref.decided_at

    if new_status != ProjectReferenceStatus.PENDING:
        from datetime import datetime

        project_ref.decided_at = datetime.utcnow()

    if new_status == ProjectReferenceStatus.APPROVED and paper_id:
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id, ResearchPaper.project_id == project.id).first()
        if not paper:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found in project")
        link_exists = (
            db.query(PaperReference)
            .filter(
                PaperReference.paper_id == paper.id,
                PaperReference.reference_id == project_ref.reference_id,
            )
            .first()
        )
        if not link_exists:
            db.add(
                PaperReference(
                    paper_id=paper.id,
                    reference_id=project_ref.reference_id,
                )
            )

    db.flush()

    reference = project_ref.reference
    event_type = {
        ProjectReferenceStatus.APPROVED: "project-reference.approved",
        ProjectReferenceStatus.REJECTED: "project-reference.rejected",
        ProjectReferenceStatus.PENDING: "project-reference.pending",
    }.get(new_status, "project-reference.updated")

    record_project_activity(
        db=db,
        project=project,
        actor=current_user,
        event_type=event_type,
        payload={
            "category": "project-reference",
            "action": event_type.split('.')[-1],
            "project_reference_id": str(project_ref.id),
            "reference_id": str(project_ref.reference_id),
            "reference_title": preview_text(reference.title if reference else None, 160),
            "status": new_status.value,
            "previous_status": previous_status.value if isinstance(previous_status, ProjectReferenceStatus) else previous_status,
            "paper_id": str(paper_id) if paper_id else None,
        },
    )

    db.commit()
    db.refresh(project_ref)
    return project_ref


@router.post("/projects/{project_id}/references/{project_reference_id}/approve")
def approve_reference_suggestion(
    project_id: str,
    project_reference_id: UUID,
    paper_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project_ref = _update_reference_status(
        project_id,
        project_reference_id,
        ProjectReferenceStatus.APPROVED,
        db=db,
        current_user=current_user,
        paper_id=paper_id,
    )
    # Queue embedding job for semantic search
    try:
        queue_library_paper_embedding_sync(project_ref.id, project_ref.project_id, db)
    except Exception as e:
        logging.getLogger(__name__).warning(f"Failed to queue embedding job: {e}")
    return {"id": str(project_ref.id), "status": project_ref.status.value}


@router.post("/projects/{project_id}/references/{project_reference_id}/reject")
def reject_reference_suggestion(
    project_id: str,
    project_reference_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project_ref = _update_reference_status(
        project_id,
        project_reference_id,
        ProjectReferenceStatus.REJECTED,
        db=db,
        current_user=current_user,
    )
    return {"id": str(project_ref.id), "status": project_ref.status.value}


@router.post(
    "/projects/{project_id}/references/{project_reference_id}/attach",
    status_code=status.HTTP_201_CREATED,
)
def attach_reference_to_paper(
    project_id: str,
    project_reference_id: UUID,
    payload: AttachReferencePayload = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    project_ref = (
        db.query(ProjectReference)
        .filter(
            ProjectReference.id == project_reference_id,
            ProjectReference.project_id == project.id,
        )
        .first()
    )
    if not project_ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project reference not found")

    if project_ref.status != ProjectReferenceStatus.APPROVED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Project reference is not approved")

    paper = (
        db.query(ResearchPaper)
        .filter(ResearchPaper.id == payload.paper_id, ResearchPaper.project_id == project.id)
        .first()
    )
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found in project")

    link_exists = (
        db.query(PaperReference)
        .filter(
            PaperReference.paper_id == paper.id,
            PaperReference.reference_id == project_ref.reference_id,
        )
        .first()
    )
    if link_exists:
        return {
            "project_reference_id": str(project_ref.id),
            "paper_reference_id": str(link_exists.id),
            "attached": True,
        }

    link = PaperReference(
        paper_id=paper.id,
        reference_id=project_ref.reference_id,
    )
    db.add(link)

    reference = project_ref.reference
    record_project_activity(
        db=db,
        project=project,
        actor=current_user,
        event_type="paper.reference-linked",
        payload={
            "category": "paper",
            "action": "reference-linked",
            "paper_id": str(paper.id),
            "paper_title": preview_text(paper.title, 160) if getattr(paper, "title", None) else None,
            "reference_id": str(project_ref.reference_id),
            "reference_title": preview_text(reference.title if reference else None, 160),
            "project_reference_id": str(project_ref.id),
        },
    )

    db.commit()
    db.refresh(link)

    return {
        "project_reference_id": str(project_ref.id),
        "paper_reference_id": str(link.id),
        "attached": True,
    }


@router.delete(
    "/projects/{project_id}/references/{project_reference_id}/papers/{paper_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def detach_reference_from_paper(
    project_id: str,
    project_reference_id: UUID,
    paper_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    project_ref = (
        db.query(ProjectReference)
        .filter(
            ProjectReference.id == project_reference_id,
            ProjectReference.project_id == project.id,
        )
        .first()
    )
    if not project_ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project reference not found")

    paper = None
    if _is_valid_uuid(paper_id):
        paper = (
            db.query(ResearchPaper)
            .filter(ResearchPaper.id == UUID(paper_id), ResearchPaper.project_id == project.id)
            .first()
        )
    if not paper:
        short_id = _parse_short_id(paper_id)
        if short_id:
            paper = (
                db.query(ResearchPaper)
                .filter(ResearchPaper.short_id == short_id, ResearchPaper.project_id == project.id)
                .first()
            )
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found in project")

    link = (
        db.query(PaperReference)
        .filter(
            PaperReference.paper_id == paper.id,
            PaperReference.reference_id == project_ref.reference_id,
        )
        .first()
    )
    if not link:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not attached to paper")

    reference = project_ref.reference

    record_project_activity(
        db=db,
        project=project,
        actor=current_user,
        event_type="paper.reference-unlinked",
        payload={
            "category": "paper",
            "action": "reference-unlinked",
            "paper_id": str(paper.id),
            "paper_title": preview_text(paper.title, 160) if getattr(paper, "title", None) else None,
            "reference_id": str(project_ref.reference_id),
            "reference_title": preview_text(reference.title if reference else None, 160),
            "project_reference_id": str(project_ref.id),
        },
    )

    db.delete(link)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/projects/{project_id}/references/{project_reference_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_project_reference(
    project_id: str,
    project_reference_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    project_ref = (
        db.query(ProjectReference)
        .filter(
            ProjectReference.project_id == project.id,
            ProjectReference.id == project_reference_id,
        )
        .first()
    )

    if not project_ref:
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    # Remove attachments to papers inside this project
    db.query(PaperReference).filter(
        PaperReference.reference_id == project_ref.reference_id,
        PaperReference.paper.has(ResearchPaper.project_id == project.id),
    ).delete(synchronize_session=False)

    db.delete(project_ref)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/papers/{paper_id}/references")
def list_references_for_paper(
    project_id: str,
    paper_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    paper = None
    if _is_valid_uuid(paper_id):
        paper = (
            db.query(ResearchPaper)
            .filter(ResearchPaper.id == UUID(paper_id), ResearchPaper.project_id == project.id)
            .first()
        )
    if not paper:
        short_id = _parse_short_id(paper_id)
        if short_id:
            paper = (
                db.query(ResearchPaper)
                .filter(ResearchPaper.short_id == short_id, ResearchPaper.project_id == project.id)
                .first()
            )
    if not paper:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found in project")

    # Ensure legacy references linked directly via reference.paper_id are represented
    legacy_refs = (
        db.query(Reference)
        .filter(Reference.paper_id == paper.id)
        .all()
    )
    for legacy in legacy_refs:
        exists = (
            db.query(PaperReference)
            .filter(
                PaperReference.paper_id == paper.id,
                PaperReference.reference_id == legacy.id,
            )
            .first()
        )
        if not exists:
            db.add(PaperReference(paper_id=paper.id, reference_id=legacy.id))
    if legacy_refs:
        db.commit()

    rows = (
        db.query(PaperReference, ProjectReference, Reference)
        .join(Reference, Reference.id == PaperReference.reference_id)
        .outerjoin(
            ProjectReference,
            (ProjectReference.reference_id == PaperReference.reference_id)
            & (ProjectReference.project_id == project.id),
        )
        .filter(PaperReference.paper_id == paper.id)
        .order_by(PaperReference.created_at.desc())
        .all()
    )

    def _serialize(link: PaperReference, project_ref: Optional[ProjectReference], reference: Reference):
        return {
            "paper_reference_id": str(link.id),
            "project_reference_id": str(project_ref.id) if project_ref else None,
            "project_reference_status": project_ref.status.value if project_ref else None,
            "reference_id": str(reference.id),
            "title": reference.title,
            "authors": reference.authors,
            "year": reference.year,
            "doi": reference.doi,
            "url": reference.url,
            "source": reference.source,
            "journal": reference.journal,
            "abstract": reference.abstract,
            "is_open_access": reference.is_open_access,
            "pdf_url": reference.pdf_url,
            "attached_at": link.created_at.isoformat() if link.created_at else None,
        }

    return {
        "project_id": str(project.id),
        "paper_id": str(paper.id),
        "references": [_serialize(*row) for row in rows],
    }
