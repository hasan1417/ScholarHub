import logging
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from sqlalchemy.exc import ProgrammingError, OperationalError
from typing import Optional, List
from app.database import get_db

logger = logging.getLogger(__name__)
from app.api.deps import get_current_user
from app.models.user import User
from app.models.reference import Reference
from app.models.document import Document, DocumentType, DocumentStatus
from app.models.research_paper import ResearchPaper
from app.models import ProjectReference, ProjectMember, ProjectRole, Project
from app.services.document_service import DocumentService
from app.services.document_processing_service import DocumentProcessingService
from app.services.reference_ingestion_service import ingest_reference_pdf
from app.services.subscription_service import SubscriptionService
from pydantic import BaseModel
from app.schemas.reference import ReferenceResponse, ReferenceList
import re

class PDFResolveRequest(BaseModel):
    url: str
    title: Optional[str] = None

class PDFResolveResponse(BaseModel):
    url: str
    pmc_url: Optional[str] = None
    pmcid: Optional[str] = None
    pdf_candidates: Optional[List[str]] = None
    chosen_pdf: Optional[str] = None
    is_open_access: Optional[bool] = None
    detail: Optional[str] = None

router = APIRouter()


class ReferenceCreateRequest(BaseModel):
    title: str
    authors: Optional[List[str]] = []
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    journal: Optional[str] = None
    abstract: Optional[str] = None
    is_open_access: Optional[bool] = False
    pdf_url: Optional[str] = None
    paper_id: Optional[str] = None  # optional immediate attachment


def _ensure_reference_permissions(
    db: Session,
    reference_id: str,
    user: User,
    *,
    allow_project_roles: bool = False,
) -> Reference:
    ref = db.query(Reference).filter(Reference.id == reference_id).first()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")

    if ref.owner_id == user.id:
        return ref

    if not allow_project_roles:
        raise HTTPException(status_code=403, detail="Not authorized to modify this reference")

    project_links = (
        db.query(ProjectReference, Project)
        .join(Project, ProjectReference.project_id == Project.id)
        .filter(ProjectReference.reference_id == reference_id)
        .all()
    )

    for project_ref, project in project_links:
        if project.created_by == user.id:
            return ref

        member = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project_ref.project_id,
                ProjectMember.user_id == user.id,
                ProjectMember.status == 'accepted',
            )
            .first()
        )
        if member:
            role_value = member.role.value if hasattr(member.role, 'value') else member.role
            if role_value in {ProjectRole.ADMIN.value, ProjectRole.EDITOR.value, ProjectRole.OWNER.value, 'admin', 'editor', 'owner'}:
                return ref

    raise HTTPException(status_code=403, detail="Not authorized to modify this reference")


@router.get("/", response_model=ReferenceList)
async def list_my_references(
    skip: int = 0,
    limit: int = 100,
    q: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        _ensure_references_schema(db)
        query = db.query(Reference).filter(Reference.owner_id == current_user.id)
        if q:
            like = f"%{q}%"
            query = query.filter(Reference.title.ilike(like))
        total = query.count()
        refs = query.order_by(Reference.created_at.desc()).offset(skip).limit(limit).all()

        # Best-effort normalization: if a reference has an uploaded document but legacy status/pdf_url
        updated = False
        for r in refs:
            try:
                if r.document_id:
                    # Ensure pdf_url present
                    if (not r.pdf_url) or r.pdf_url.strip() == "":
                        r.pdf_url = f"/api/v1/documents/{r.document_id}/download"
                        updated = True
                    # Upgrade status based on document processing state
                    try:
                        doc = db.query(Document).filter(Document.id == r.document_id).first()
                        if doc and doc.status == DocumentStatus.PROCESSED:
                            if r.status != 'analyzed':
                                r.status = 'analyzed'
                                updated = True
                        else:
                            if r.status == 'pending':
                                r.status = 'ingested'
                                updated = True
                    except Exception:
                        pass
            except Exception:
                pass
        if updated:
            db.commit()
        return ReferenceList(references=refs, total=total)
    except (ProgrammingError, OperationalError) as e:
        # Likely missing migration for owner_id or altered schema
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="References schema mismatch. Please run database migrations (alembic upgrade head)."
        )


@router.post("/", response_model=ReferenceResponse, status_code=status.HTTP_201_CREATED)
async def create_reference(
    payload: ReferenceCreateRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Check subscription limit for total references
    allowed, current, limit = SubscriptionService.check_resource_limit(
        db, current_user.id, "references_total"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "references_total",
                "current": current,
                "limit": limit,
                "message": f"You have reached your reference library limit ({current}/{limit}). Upgrade to Pro for more references.",
            },
        )

    try:
        _ensure_references_schema(db)
        # Prevent duplicates in the target scope (paper-specific or user library)
        def _normalize_title(s: str) -> str:
            return re.sub(r"\s+", " ", (s or "").strip()).lower()

        try:
            dup = None
            norm_in = _normalize_title(payload.title)
            base_q = db.query(Reference).filter(Reference.owner_id == current_user.id)
            if payload.paper_id:
                base_q = base_q.filter(Reference.paper_id == payload.paper_id)
            existing = base_q.all()
            for er in existing:
                if payload.doi and er.doi and er.doi.strip().lower() == payload.doi.strip().lower():
                    dup = er
                    break
                if _normalize_title(er.title) == norm_in and (not payload.year or not er.year or er.year == payload.year):
                    dup = er
                    break
            if dup:
                # Soft-update missing fields on duplicate
                updated = False
                if not dup.journal and payload.journal:
                    dup.journal = payload.journal; updated = True
                if (not dup.year) and payload.year:
                    dup.year = payload.year; updated = True
                if (not dup.authors) and (payload.authors or []):
                    dup.authors = payload.authors; updated = True
                if (not dup.abstract) and payload.abstract:
                    dup.abstract = payload.abstract; updated = True
                if (not dup.doi) and payload.doi:
                    dup.doi = payload.doi; updated = True
                if (not dup.pdf_url) and payload.pdf_url:
                    dup.pdf_url = payload.pdf_url; updated = True
                if (not dup.paper_id) and payload.paper_id:
                    dup.paper_id = payload.paper_id; updated = True
                if updated:
                    db.commit(); db.refresh(dup)
                # Enrich duplicate if it's still missing metadata
                from app.services.reference_enrichment_service import enrich_and_ingest_reference, _needs_enrichment
                if _needs_enrichment(dup):
                    background_tasks.add_task(enrich_and_ingest_reference, str(dup.id))
                return dup
        except Exception:
            # Non-fatal; proceed with creation
            pass

        ref = Reference(
            owner_id=current_user.id,
            paper_id=payload.paper_id,
            title=payload.title,
            authors=payload.authors or [],
            year=payload.year,
            doi=payload.doi,
            url=payload.url,
            source=payload.source,
            journal=payload.journal,
            abstract=payload.abstract,
            is_open_access=bool(payload.is_open_access),
            pdf_url=payload.pdf_url,
            status="pending",
        )
        db.add(ref)
        db.commit()
        db.refresh(ref)

        # Enrich metadata (authors, year, abstract, PDF URL) via CrossRef/Unpaywall/S2
        # and auto-ingest PDF if found — runs as a background task
        from app.services.reference_enrichment_service import enrich_and_ingest_reference
        background_tasks.add_task(enrich_and_ingest_reference, str(ref.id))

        return ref
    except (ProgrammingError, OperationalError) as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="References schema mismatch. Please run database migrations (alembic upgrade head)."
        )


@router.post("/{reference_id}/attach-to-paper", response_model=ReferenceResponse)
async def attach_reference_to_paper(
    reference_id: str,
    paper_id: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = _ensure_reference_permissions(db, reference_id, current_user, allow_project_roles=False)
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    if paper.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Cannot attach to a paper you don't own")
    ref.paper_id = paper_id
    db.commit()
    db.refresh(ref)
    return ref


@router.post("/{reference_id}/upload-pdf", response_model=ReferenceResponse)
async def upload_reference_pdf(
    reference_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = _ensure_reference_permissions(db, reference_id, current_user, allow_project_roles=True)
    content = await file.read()
    # Accept application/pdf and application/octet-stream (common for publisher CDNs).
    # Validate actual content via PDF magic bytes (%PDF-) for safety.
    allowed_types = {"application/pdf", "application/octet-stream"}
    if file.content_type not in allowed_types or not content[:5].startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    ds = DocumentService()
    file_path = await ds.save_uploaded_file(content, file.filename)
    document = Document(
        filename=file.filename,
        original_filename=file.filename,
        file_path=file_path,
        file_size=len(content),
        mime_type='application/pdf',
        document_type=DocumentType.PDF,
        file_hash=ds.duplicate_detector.calculate_file_hash(content),
        title=ref.title,
        doi=ref.doi,
        journal=ref.journal,
        owner_id=current_user.id,
        paper_id=ref.paper_id,
        status=DocumentStatus.PROCESSING,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    # Store document ID before processing (in case session gets rolled back)
    document_id = document.id

    # process + embed using existing system (best-effort)
    try:
        await ds.process_document(db, document, content, None)
        DocumentProcessingService().embed_document_chunks(db, str(document_id))

        # Link document chunks to this reference for reference-based RAG
        try:
            from app.models.document_chunk import DocumentChunk
            chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
            for chunk in chunks:
                chunk.reference_id = str(ref.id)
            db.commit()
            logger.info(f"Linked {len(chunks)} chunks to reference {ref.id}")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to link chunks to reference {ref.id}: {e}")

        # Mark document processed
        document.status = DocumentStatus.PROCESSED
        # update reference status to analyzed when processing completes
        ref.status = 'analyzed'
    except Exception as e:
        # Rollback any failed transaction and leave status as ingested
        db.rollback()
        logger.warning(f"Document processing failed for reference {ref.id}: {e}")
        ref.status = 'ingested'
        # Re-fetch document after rollback
        document = db.query(Document).filter(Document.id == document_id).first()

    # update reference
    ref.document_id = document_id
    # Provide a direct API download link for the uploaded PDF
    ref.pdf_url = f"/api/v1/documents/{document.id}/download"
    ref.is_open_access = True
    db.commit()
    db.refresh(ref)
    return ref


@router.post("/{reference_id}/ingest-pdf", response_model=ReferenceResponse)
async def ingest_reference_pdf_endpoint(
    reference_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = _ensure_reference_permissions(db, reference_id, current_user, allow_project_roles=True)

    if not ref.pdf_url:
        raise HTTPException(status_code=400, detail="Reference does not have a PDF URL to ingest")

    success = ingest_reference_pdf(db, ref, owner_id=str(current_user.id))
    if not success:
        raise HTTPException(status_code=400, detail="Unable to ingest PDF for this reference")

    db.refresh(ref)
    return ref


@router.delete("/{reference_id}", response_model=dict)
async def delete_reference(
    reference_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ref = db.query(Reference).filter(Reference.id == reference_id, Reference.owner_id == current_user.id).first()
    if not ref:
        raise HTTPException(status_code=404, detail="Reference not found")
    db.delete(ref)
    db.commit()
    return {"message": "Reference deleted"}


# Removed: resolve-pdf-by-id endpoint for references (feature deprecated)


@router.post("/debug/resolve-pdf", response_model=PDFResolveResponse)
async def resolve_pdf_from_url(
    payload: PDFResolveRequest,
    current_user: User = Depends(get_current_user),
):
    """Disabled debug endpoint kept only for backward-compatible routing."""
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Debug PDF resolver is disabled",
    )


def _ensure_references_schema(db: Session) -> None:
    """Best-effort runtime schema alignment to prevent 500s when migrations weren't applied.
    Safe to call on every request; no-op if schema already correct.
    """
    try:
        engine = db.get_bind()
        insp = inspect(engine)
        tables = insp.get_table_names()
        if 'references' not in tables:
            # Create table if it doesn't exist (minimal set of columns used by API)
            engine.execute(text(
                'CREATE TABLE IF NOT EXISTS "references" ('
                'id uuid PRIMARY KEY,'
                'paper_id uuid NULL REFERENCES research_papers(id) ON DELETE CASCADE,'
                'owner_id uuid NULL REFERENCES users(id) ON DELETE CASCADE,'
                'title VARCHAR(500) NOT NULL,'
                'authors TEXT[],'
                'year INTEGER,'
                'doi VARCHAR(255),'
                'url VARCHAR(1000),'
                'source VARCHAR(100),'
                'entry_type VARCHAR(100),'
                'journal VARCHAR(500),'
                'abstract TEXT,'
                'is_open_access BOOLEAN DEFAULT FALSE,'
                'pdf_url VARCHAR(1000),'
                'status VARCHAR(50) DEFAULT '"'"'pending'"'"','
                'document_id uuid NULL REFERENCES documents(id),'
                'summary TEXT,'
                'key_findings TEXT[],'
                'methodology TEXT,'
                'limitations TEXT[],'
                'relevance_score FLOAT,'
                'created_at TIMESTAMPTZ DEFAULT now(),'
                'updated_at TIMESTAMPTZ DEFAULT now()'
                ')'
            ))
            return
        # Table exists; ensure required columns/properties
        cols = {c['name']: c for c in insp.get_columns('references')}
        if 'owner_id' not in cols:
            engine.execute(text('ALTER TABLE "references" ADD COLUMN owner_id uuid'))
        if 'entry_type' not in cols:
            engine.execute(text('ALTER TABLE "references" ADD COLUMN entry_type VARCHAR(100)'))
        # Ensure paper_id nullable
        if 'paper_id' in cols and not cols['paper_id'].get('nullable', True):
            engine.execute(text('ALTER TABLE "references" ALTER COLUMN paper_id DROP NOT NULL'))
    except Exception:
        # Silent best-effort; fall back to API-level error messaging if DB still mismatched
        pass
