from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Optional
from uuid import UUID

import httpx
import redis
from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response, UploadFile, File as FastAPIFile, status
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
from pydantic import BaseModel, Field


router = APIRouter()
logger = logging.getLogger(__name__)


def _guard_feature() -> None:
    if not settings.PROJECT_REFERENCE_SUGGESTIONS_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project references feature disabled")


class ProjectReferenceResponse(dict):
    """Lightweight serializer to avoid creating a dedicated Pydantic model right now."""


# ──────────────────────────────────────────────────────────────
# Citation graph
# ──────────────────────────────────────────────────────────────

CITATION_GRAPH_CACHE_TTL = 60 * 60 * 24  # 24 hours
CITATION_GRAPH_CACHE_PREFIX = "citation_graph:"
SEMANTIC_SCHOLAR_TIMEOUT = 5  # seconds
MAX_GRAPH_NODES = 100
MAX_EXTERNAL_PER_LIBRARY = 2


_redis_singleton: redis.Redis | None = None
_redis_initialized: bool = False


def _redis_client() -> redis.Redis | None:
    global _redis_singleton, _redis_initialized
    if _redis_initialized:
        return _redis_singleton
    _redis_initialized = True
    try:
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
        )
        client.ping()
        _redis_singleton = client
    except Exception:
        _redis_singleton = None
    return _redis_singleton


_S2_LOCK = asyncio.Lock()
_S2_LAST_REQUEST: float = 0.0


def _normalize_doi(doi: str) -> str:
    """Strip URL prefixes from DOIs (e.g. 'https://doi.org/10.xxx' -> '10.xxx')."""
    return re.sub(r'^https?://(dx\.)?doi\.org/', '', doi).strip()


async def _fetch_semantic_scholar(doi: str) -> dict | None:
    """Fetch references and citations for a DOI from Semantic Scholar.

    Enforces 1 request/second rate limit (S2 API key constraint).
    """
    global _S2_LAST_REQUEST
    doi = _normalize_doi(doi)
    url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
    params = {"fields": "references.externalIds,references.title,citations.externalIds,citations.title"}
    headers: dict[str, str] = {}
    if settings.SEMANTIC_SCHOLAR_API_KEY:
        headers["Authorization"] = f"Bearer {settings.SEMANTIC_SCHOLAR_API_KEY}"
    async with _S2_LOCK:
        # Enforce 1 req/sec rate limit
        import time
        elapsed = time.monotonic() - _S2_LAST_REQUEST
        if elapsed < 1.05:
            await asyncio.sleep(1.05 - elapsed)
        try:
            async with httpx.AsyncClient(timeout=SEMANTIC_SCHOLAR_TIMEOUT) as client:
                _S2_LAST_REQUEST = time.monotonic()
                resp = await client.get(url, params=params, headers=headers)
                if resp.status_code == 200:
                    return resp.json()
                if resp.status_code == 429:
                    logger.warning("Semantic Scholar rate-limited (429) for DOI %s", doi)
                elif resp.status_code == 403:
                    logger.warning("Semantic Scholar auth failed (403) for DOI %s — check API key", doi)
                else:
                    logger.debug("Semantic Scholar returned %d for DOI %s", resp.status_code, doi)
        except Exception as exc:
            logger.debug("Semantic Scholar fetch failed for DOI %s: %s", doi, exc)
    return None


def _extract_doi(external_ids: dict | None) -> str | None:
    if not external_ids:
        return None
    return external_ids.get("DOI") or external_ids.get("doi")


@router.get("/projects/{project_id}/references/citation-graph")
async def get_citation_graph(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build a citation graph showing how papers in the project library cite each other."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    cache_key = f"{CITATION_GRAPH_CACHE_PREFIX}{project.id}"

    # Try cache first
    rc = _redis_client()
    if rc:
        try:
            cached = rc.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception:
            pass

    # Fetch approved references
    project_refs = (
        db.query(ProjectReference)
        .filter(
            ProjectReference.project_id == project.id,
            ProjectReference.status == ProjectReferenceStatus.APPROVED,
        )
        .all()
    )

    if not project_refs:
        return {"nodes": [], "edges": [], "warnings": []}

    # Build library nodes indexed by DOI for fast lookup
    nodes_by_id: dict[str, dict] = {}
    doi_to_node_id: dict[str, str] = {}
    library_dois: set[str] = set()

    for pr in project_refs:
        ref = pr.reference
        if not ref:
            continue
        node_id = str(pr.id)
        authors = ref.authors or []
        node = {
            "id": node_id,
            "title": ref.title or "Untitled",
            "authors": authors[:5],
            "year": ref.year,
            "doi": ref.doi,
            "in_library": True,
            "type": "library",
        }
        nodes_by_id[node_id] = node
        if ref.doi:
            norm_doi = _normalize_doi(ref.doi).lower()
            doi_to_node_id[norm_doi] = node_id
            library_dois.add(norm_doi)

    # For each library paper with a DOI, fetch from Semantic Scholar concurrently
    refs_with_doi = [(pr, pr.reference) for pr in project_refs if pr.reference and pr.reference.doi]
    s2_results = await asyncio.gather(
        *[_fetch_semantic_scholar(ref.doi) for _pr, ref in refs_with_doi],
        return_exceptions=True,
    )

    # Count failures for warnings
    failed_count = sum(
        1 for r in s2_results if r is None or isinstance(r, BaseException)
    )
    warnings: list[str] = []
    if failed_count > 0:
        warnings.append(f"{failed_count} paper(s) could not be fetched from Semantic Scholar")

    edges: list[dict] = []
    seen_edges: set[tuple[str, str]] = set()
    external_counter = 0

    def _add_edge(source: str, target: str) -> None:
        key = (source, target)
        if key not in seen_edges:
            seen_edges.add(key)
            edges.append({"source": source, "target": target, "type": "cites"})

    for (pr, ref), data in zip(refs_with_doi, s2_results):
        if data is None or isinstance(data, BaseException):
            continue

        lib_node_id = str(pr.id)
        added_for_this = 0

        # Process references (papers this library paper cites)
        for cited in (data.get("references") or []):
            if added_for_this >= MAX_EXTERNAL_PER_LIBRARY and len(nodes_by_id) >= MAX_GRAPH_NODES:
                break
            cited_doi = _extract_doi(cited.get("externalIds"))
            cited_title = cited.get("title") or "Untitled"

            if cited_doi and cited_doi.lower() in doi_to_node_id:
                target_id = doi_to_node_id[cited_doi.lower()]
                _add_edge(lib_node_id, target_id)
            else:
                if added_for_this >= MAX_EXTERNAL_PER_LIBRARY:
                    continue
                if len(nodes_by_id) >= MAX_GRAPH_NODES:
                    continue
                ext_id = f"ext_cited_{cited_doi.lower()}" if cited_doi else f"ext_cited_{external_counter}"
                external_counter += 1
                if ext_id not in nodes_by_id:
                    nodes_by_id[ext_id] = {
                        "id": ext_id,
                        "title": cited_title,
                        "authors": [],
                        "year": None,
                        "doi": cited_doi,
                        "in_library": False,
                        "type": "cited",
                    }
                    if cited_doi:
                        doi_to_node_id[cited_doi.lower()] = ext_id
                _add_edge(lib_node_id, ext_id)
                added_for_this += 1

        # Process citations (papers that cite this library paper)
        added_citing = 0
        for citing in (data.get("citations") or []):
            if added_citing >= MAX_EXTERNAL_PER_LIBRARY and len(nodes_by_id) >= MAX_GRAPH_NODES:
                break
            citing_doi = _extract_doi(citing.get("externalIds"))
            citing_title = citing.get("title") or "Untitled"

            if citing_doi and citing_doi.lower() in doi_to_node_id:
                source_id = doi_to_node_id[citing_doi.lower()]
                _add_edge(source_id, lib_node_id)
            else:
                if added_citing >= MAX_EXTERNAL_PER_LIBRARY:
                    continue
                if len(nodes_by_id) >= MAX_GRAPH_NODES:
                    continue
                ext_id = f"ext_citing_{citing_doi.lower()}" if citing_doi else f"ext_citing_{external_counter}"
                external_counter += 1
                if ext_id not in nodes_by_id:
                    nodes_by_id[ext_id] = {
                        "id": ext_id,
                        "title": citing_title,
                        "authors": [],
                        "year": None,
                        "doi": citing_doi,
                        "in_library": False,
                        "type": "citing",
                    }
                    if citing_doi:
                        doi_to_node_id[citing_doi.lower()] = ext_id
                _add_edge(ext_id, lib_node_id)
                added_citing += 1

    result = {
        "nodes": list(nodes_by_id.values()),
        "edges": edges,
        "warnings": warnings,
    }

    # Cache result
    if rc:
        try:
            rc.setex(cache_key, CITATION_GRAPH_CACHE_TTL, json.dumps(result))
        except Exception:
            pass

    return result


class AttachReferencePayload(BaseModel):
    paper_id: UUID


from app.utils.id_parsing import is_valid_uuid as _is_valid_uuid, parse_short_id as _parse_short_id


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


class SuggestCitationsPayload(BaseModel):
    text: str = Field(..., min_length=1, max_length=10000)
    limit: int = Field(default=3, ge=1, le=10)


@router.post("/projects/{project_id}/references/suggest-citations")
async def suggest_citations(
    project_id: str,
    payload: SuggestCitationsPayload,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suggest citations from the project library based on semantic similarity to the given text."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    from app.models.paper_embedding import PaperEmbedding
    from app.services.embedding_service import get_embedding_service
    from sqlalchemy import text as sa_text

    # Embed the query text
    try:
        embedding_service = get_embedding_service()
        query_embedding = await embedding_service.embed(payload.text)
    except Exception as e:
        logger.error("Citation suggestion embedding failed: %s", e)
        return {"suggestions": []}

    embedding_str = "[" + ",".join(str(x) for x in query_embedding) + "]"

    sql = sa_text("""
        SELECT
            pr.id as project_reference_id,
            r.id as reference_id,
            r.title,
            r.authors,
            r.year,
            1 - (pe.embedding <=> :query_embedding) as similarity
        FROM paper_embeddings pe
        JOIN project_references pr ON pe.project_reference_id = pr.id
        JOIN "references" r ON pr.reference_id = r.id
        WHERE pr.project_id = :project_id
            AND pr.status = 'approved'
            AND 1 - (pe.embedding <=> :query_embedding) > 0.15
        ORDER BY pe.embedding <=> :query_embedding
        LIMIT :limit
    """)

    try:
        result = db.execute(
            sql,
            {
                "query_embedding": embedding_str,
                "project_id": str(project.id),
                "limit": payload.limit,
            },
        )
        rows = result.fetchall()
    except Exception as e:
        logger.error("Citation suggestion vector query failed: %s", e)
        return {"suggestions": []}

    # Disambiguate citation keys across results
    class _RefProxy:
        def __init__(self, rid, authors, year):
            self.id = rid
            self.authors = authors
            self.year = year

    proxies = [_RefProxy(row.reference_id, row.authors or [], row.year) for row in rows]
    key_map = _disambiguate_cite_keys(proxies)

    suggestions = []
    for row in rows:
        suggestions.append({
            "reference_id": str(row.reference_id),
            "title": row.title,
            "authors": row.authors or [],
            "year": row.year,
            "citation_key": key_map.get(row.reference_id, _generate_cite_key(row.authors or [], row.year)),
            "similarity": round(float(row.similarity), 4),
        })

    return {"suggestions": suggestions}


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


class IngestionStatusRequest(BaseModel):
    reference_ids: list[str]


@router.post("/projects/{project_id}/references/ingestion-status")
def get_ingestion_status(
    project_id: str,
    payload: IngestionStatusRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    statuses: dict[str, str] = {}
    for ref_id_str in payload.reference_ids[:200]:
        try:
            ref_id = UUID(ref_id_str)
        except (ValueError, AttributeError):
            continue

        ref = db.query(Reference).filter(Reference.id == ref_id).first()
        if not ref:
            continue

        _sync_reference_analysis_state(ref)

        if ref.status == 'analyzed':
            statuses[ref_id_str] = 'success'
        elif ref.status == 'ingested':
            statuses[ref_id_str] = 'pending'
        elif ref.document is not None:
            statuses[ref_id_str] = 'pending'
        elif ref.pdf_url:
            statuses[ref_id_str] = 'failed'
        else:
            statuses[ref_id_str] = 'no_pdf'

    db.commit()
    return {"statuses": statuses}


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


# ──────────────────────────────────────────────────────────────
# BibTeX import / export
# ──────────────────────────────────────────────────────────────

def _parse_bibtex(raw: str) -> list[dict]:
    """Minimal BibTeX parser. Returns a list of dicts with extracted fields."""
    entries: list[dict] = []
    # Match @type{key, ... } blocks
    pattern = re.compile(r"@(\w+)\s*\{([^,]*),", re.IGNORECASE)
    positions = [(m.start(), m.group(1), m.group(2).strip()) for m in pattern.finditer(raw)]

    for idx, (start, entry_type, cite_key) in enumerate(positions):
        # Find the body between this entry's opening brace and its closing brace
        brace_start = raw.index("{", start)
        depth = 0
        end = brace_start
        for i in range(brace_start, len(raw)):
            if raw[i] == "{":
                depth += 1
            elif raw[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i
                    break
        body = raw[brace_start + 1 : end]
        # Remove the cite_key prefix (everything up to and including first comma)
        first_comma = body.find(",")
        if first_comma >= 0:
            body = body[first_comma + 1 :]

        # Extract field = {value} or field = "value" pairs
        fields: dict[str, str] = {}
        field_re = re.compile(r"(\w+)\s*=\s*[{\"](.+?)[}\"]", re.DOTALL)
        for fm in field_re.finditer(body):
            fields[fm.group(1).lower().strip()] = fm.group(2).strip()

        # Build entry dict
        title = fields.get("title", "").strip()
        if not title:
            continue  # skip entries without a title

        authors_raw = fields.get("author", "")
        authors = [a.strip() for a in authors_raw.split(" and ")] if authors_raw else []

        year_str = fields.get("year", "")
        year = None
        if year_str:
            try:
                year = int(re.sub(r"\D", "", year_str)[:4])
            except (ValueError, IndexError):
                pass

        journal = fields.get("journal") or fields.get("booktitle") or None
        doi = fields.get("doi") or None
        abstract = fields.get("abstract") or None

        entries.append({
            "title": title,
            "authors": authors,
            "year": year,
            "journal": journal,
            "doi": doi,
            "abstract": abstract,
            "entry_type": entry_type.lower(),
            "cite_key": cite_key,
        })

    return entries


def _generate_cite_key(authors: list[str] | None, year: int | None) -> str:
    """Generate a citation key from first author lastname + year."""
    lastname = "unknown"
    if authors and len(authors) > 0:
        first = authors[0]
        if "," in first:
            lastname = first.split(",")[0].strip()
        else:
            parts = first.strip().split()
            lastname = parts[-1] if parts else "unknown"
    lastname = re.sub(r"[^a-zA-Z]", "", lastname).lower() or "unknown"
    yr = str(year) if year else "XXXX"
    return f"{lastname}{yr}"


def _disambiguate_cite_keys(refs: list) -> dict:
    """Generate unique cite keys for a list of references, appending a/b/c on collision."""
    keys: dict = {}  # ref -> key
    used: dict = {}  # base_key -> count
    for ref in refs:
        authors = ref.authors or []
        base = _generate_cite_key(authors, ref.year)
        count = used.get(base, 0)
        used[base] = count + 1
        if count == 0:
            keys[ref.id] = base
        else:
            suffix = chr(ord("a") + count)
            keys[ref.id] = f"{base}{suffix}"
    # Go back and add 'a' suffix to the first occurrence if there were collisions
    for ref in refs:
        authors = ref.authors or []
        base = _generate_cite_key(authors, ref.year)
        if used[base] > 1 and keys[ref.id] == base:
            keys[ref.id] = f"{base}a"
    return keys


def _reference_to_bibtex(ref: Reference, cite_key: str | None = None, entry_type: str = "article") -> str:
    """Convert a Reference model instance to a BibTeX entry string."""
    authors = ref.authors or []
    if not cite_key:
        cite_key = _generate_cite_key(authors, ref.year)
    lines = [f"@{entry_type}{{{cite_key},"]
    if ref.title:
        lines.append(f"  title = {{{ref.title}}},")
    if authors:
        lines.append(f"  author = {{{' and '.join(authors)}}},")
    if ref.year:
        lines.append(f"  year = {{{ref.year}}},")
    if ref.journal:
        lines.append(f"  journal = {{{ref.journal}}},")
    if ref.doi:
        lines.append(f"  doi = {{{ref.doi}}},")
    if ref.abstract:
        lines.append(f"  abstract = {{{ref.abstract}}},")
    if ref.url:
        lines.append(f"  url = {{{ref.url}}},")
    lines.append("}")
    return "\n".join(lines)


@router.post("/projects/{project_id}/references/import-bibtex")
def import_bibtex(
    project_id: str,
    file: UploadFile = FastAPIFile(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Import references from a .bib file into the project library."""
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    try:
        raw = file.file.read().decode("utf-8", errors="replace")
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unable to read uploaded file")

    entries = _parse_bibtex(raw)
    if not entries:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid BibTeX entries found in file")

    imported = 0
    skipped = 0
    errors: list[str] = []

    # Accumulate valid entries first, then bulk insert to avoid transaction issues
    valid_refs: list[dict] = []

    for entry in entries:
        # Check for duplicate by DOI within the project
        if entry.get("doi"):
            existing = (
                db.query(ProjectReference)
                .join(Reference, Reference.id == ProjectReference.reference_id)
                .filter(
                    ProjectReference.project_id == project.id,
                    Reference.doi == entry["doi"],
                )
                .first()
            )
            if existing:
                skipped += 1
                continue

        valid_refs.append(entry)

    # Insert all valid entries in a single transaction
    from datetime import datetime
    for entry in valid_refs:
        try:
            ref = Reference(
                owner_id=current_user.id,
                title=entry["title"],
                authors=entry.get("authors") or None,
                year=entry.get("year"),
                journal=entry.get("journal"),
                doi=entry.get("doi"),
                abstract=entry.get("abstract"),
                source="bibtex",
            )
            db.add(ref)
            db.flush()

            pr = ProjectReference(
                project_id=project.id,
                reference_id=ref.id,
                status=ProjectReferenceStatus.APPROVED,
                confidence=1.0,
                decided_by=current_user.id,
            )
            pr.decided_at = datetime.utcnow()
            db.add(pr)
            db.flush()

            imported += 1
        except Exception as exc:
            logger.warning("BibTeX import error for entry '%s': %s", entry.get("title", "?"), exc)
            errors.append(f"Failed to import: {entry.get('title', 'unknown')}")

    if imported > 0:
        try:
            db.commit()
        except Exception:
            db.rollback()
            raise HTTPException(status_code=500, detail="Failed to save imported references")

    return {"imported": imported, "skipped": skipped, "errors": errors}


@router.get("/projects/{project_id}/references/export-bibtex")
def export_bibtex(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export all approved project references as a .bib file."""
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    project_refs = (
        db.query(ProjectReference)
        .filter(
            ProjectReference.project_id == project.id,
            ProjectReference.status == ProjectReferenceStatus.APPROVED,
        )
        .all()
    )

    all_refs = [pr.reference for pr in project_refs if pr.reference]
    key_map = _disambiguate_cite_keys(all_refs)

    bib_entries: list[str] = []
    for ref in all_refs:
        bib_entries.append(_reference_to_bibtex(ref, cite_key=key_map.get(ref.id)))

    bibtex_str = "\n\n".join(bib_entries) + "\n" if bib_entries else "% No references to export\n"

    return Response(
        content=bibtex_str,
        media_type="text/plain",
        headers={"Content-Disposition": "attachment; filename=references.bib"},
    )


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
        document = reference.document if reference else None
        document_id = str(document.id) if document else None
        document_status = None
        document_download_url = None
        pdf_processed = False

        if document:
            status_attr = getattr(document.status, "value", None)
            document_status = status_attr or str(document.status)
            document_download_url = f"/api/v1/documents/{document.id}/download"
            pdf_processed = bool(getattr(document, "is_processed_for_ai", False))

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
            "pdf_processed": pdf_processed,
            "document_id": document_id,
            "document_status": document_status,
            "document_download_url": document_download_url,
            "attached_at": link.created_at.isoformat() if link.created_at else None,
        }

    return {
        "project_id": str(project.id),
        "paper_id": str(paper.id),
        "references": [_serialize(*row) for row in rows],
    }
