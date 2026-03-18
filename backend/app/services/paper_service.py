"""
Paper Service - Centralized paper creation and management.

All paper creation should go through this service to ensure:
- Consistent paper structure
- Initial snapshot creation for version history
- Proper member/owner setup
"""
import logging
import hashlib
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.research_paper import ResearchPaper
from app.models.paper_member import PaperMember, PaperRole
from app.models.document_snapshot import DocumentSnapshot
from app.models.user import User
from app.models.project import Project

logger = logging.getLogger(__name__)
SNAPSHOT_SEQUENCE_RETRY_COUNT = 3


def compute_snapshot_content_hash(
    text: Optional[str],
    materialized_files: Optional[Dict[str, str]] = None,
) -> str:
    """Return a stable short hash for snapshot deduplication."""
    if not materialized_files:
        normalized_text = text or ""
        return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16]

    payload = {
        "materialized_text": text or "",
        "materialized_files": materialized_files,
    }
    normalized_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(normalized_payload.encode("utf-8")).hexdigest()[:16]


def get_next_snapshot_sequence_number(db: Session, paper_id: UUID) -> int:
    """Get the next sequence number for a paper snapshot."""
    max_seq = db.query(func.max(DocumentSnapshot.sequence_number)).filter(
        DocumentSnapshot.paper_id == paper_id
    ).scalar()
    return (max_seq or 0) + 1


def _is_snapshot_sequence_conflict(exc: IntegrityError) -> bool:
    """Return True when the error is the paper+sequence unique constraint."""
    constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
    if constraint_name == "uq_document_snapshots_paper_sequence":
        return True

    message = str(exc.orig)
    return "uq_document_snapshots_paper_sequence" in message or (
        "document_snapshots" in message and "sequence_number" in message
    )


def add_snapshot_with_retry(
    db: Session,
    *,
    paper_id: UUID,
    yjs_state: bytes,
    materialized_text: Optional[str],
    materialized_files: Optional[Dict[str, str]] = None,
    snapshot_type: str,
    label: Optional[str] = None,
    created_by: Optional[UUID] = None,
) -> DocumentSnapshot:
    """
    Stage a snapshot in the current transaction, retrying sequence allocation on conflicts.

    The snapshot is flushed inside a savepoint so callers can safely use this while other
    model changes are pending in the same transaction.
    """
    text_length = len(materialized_text) if materialized_text is not None else 0
    content_hash = compute_snapshot_content_hash(materialized_text, materialized_files)

    last_error: Optional[IntegrityError] = None
    for attempt in range(SNAPSHOT_SEQUENCE_RETRY_COUNT):
        snapshot = DocumentSnapshot(
            paper_id=paper_id,
            yjs_state=yjs_state,
            materialized_text=materialized_text,
            materialized_files=materialized_files,
            snapshot_type=snapshot_type,
            label=label,
            created_by=created_by,
            sequence_number=get_next_snapshot_sequence_number(db, paper_id),
            text_length=text_length,
            content_hash=content_hash,
        )

        try:
            with db.begin_nested():
                db.add(snapshot)
                db.flush()
            return snapshot
        except IntegrityError as exc:
            last_error = exc
            if not _is_snapshot_sequence_conflict(exc) or attempt == SNAPSHOT_SEQUENCE_RETRY_COUNT - 1:
                raise
            logger.info(
                "Retrying snapshot sequence allocation for paper %s after conflict (attempt %s/%s)",
                paper_id,
                attempt + 1,
                SNAPSHOT_SEQUENCE_RETRY_COUNT,
            )

    if last_error:
        raise last_error

    raise RuntimeError("Snapshot creation failed without a captured error")


def create_paper(
    db: Session,
    *,
    title: str,
    owner_id: UUID,
    project_id: Optional[UUID] = None,
    content: Optional[str] = None,
    content_json: Optional[Dict[str, Any]] = None,
    abstract: Optional[str] = None,
    paper_type: str = "research",
    status: str = "draft",
    slug: Optional[str] = None,
    short_id: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    objectives: Optional[List[str]] = None,
    snapshot_label: str = "Initial version",
    extra_fields: Optional[Dict[str, Any]] = None,
) -> ResearchPaper:
    """
    Create a paper with proper initialization and initial snapshot.

    This is the canonical way to create papers - ensures:
    1. Paper is created with all required fields
    2. Owner is added as paper member with OWNER role
    3. Initial snapshot is created if paper has content

    Args:
        db: Database session
        title: Paper title
        owner_id: User ID of the paper owner
        project_id: Optional project ID
        content: Legacy content field (plain text)
        content_json: Structured content (latex_source, rich_text, etc.)
        abstract: Paper abstract
        paper_type: Type of paper (research, review, etc.)
        status: Paper status (draft, published, etc.)
        slug: URL-friendly slug
        short_id: Short ID for URLs
        keywords: List of keywords
        objectives: List of objectives
        snapshot_label: Label for the initial snapshot
        extra_fields: Any additional fields to set on the paper

    Returns:
        The created ResearchPaper instance
    """
    # Ensure content_json always has authoring_mode=latex
    if content_json is None:
        content_json = {"authoring_mode": "latex", "latex_source": ""}
    elif isinstance(content_json, dict) and "authoring_mode" not in content_json:
        content_json["authoring_mode"] = "latex"

    # Build paper kwargs
    paper_kwargs = {
        "title": title,
        "owner_id": owner_id,
        "project_id": project_id,
        "content": content,
        "content_json": content_json,
        "abstract": abstract,
        "paper_type": paper_type,
        "status": status,
        "slug": slug,
        "short_id": short_id,
        "keywords": keywords or [],
        "objectives": objectives,
    }

    # Add any extra fields
    if extra_fields:
        paper_kwargs.update(extra_fields)

    # Remove None values to let defaults apply
    paper_kwargs = {k: v for k, v in paper_kwargs.items() if v is not None}

    # Create paper
    paper = ResearchPaper(**paper_kwargs)
    db.add(paper)
    db.commit()
    db.refresh(paper)

    # Add owner as paper member with OWNER role
    owner_member = PaperMember(
        paper_id=paper.id,
        user_id=owner_id,
        role=PaperRole.OWNER,
        status="accepted",
        joined_at=datetime.now(timezone.utc),
    )
    db.add(owner_member)
    db.commit()

    # Create initial snapshot if paper has content
    _create_initial_snapshot(
        db=db,
        paper=paper,
        creator_id=owner_id,
        label=snapshot_label,
    )

    return paper


def _create_initial_snapshot(
    db: Session,
    paper: ResearchPaper,
    creator_id: UUID,
    label: str = "Initial version",
) -> Optional[DocumentSnapshot]:
    """
    Create an initial snapshot for a paper if it has content.

    This ensures users can always restore to the original version.
    """
    try:
        # Extract content for snapshot
        materialized_text = _extract_materialized_text(paper)
        materialized_files = _extract_materialized_files(paper)

        if not materialized_text or not materialized_text.strip():
            logger.debug("No content to snapshot for paper %s", paper.id)
            return None

        snapshot = add_snapshot_with_retry(
            db,
            paper_id=paper.id,
            yjs_state=b"",  # No Yjs state for API-created papers
            materialized_text=materialized_text,
            materialized_files=materialized_files,
            snapshot_type="auto",
            label=label,
            created_by=creator_id,
        )
        db.commit()
        db.refresh(snapshot)

        logger.info(
            "Created initial snapshot for paper %s: seq=%s, len=%s",
            paper.id, snapshot.sequence_number, snapshot.text_length
        )
        return snapshot

    except Exception as e:
        logger.warning(
            "Failed to create initial snapshot for paper %s: %s",
            paper.id, str(e)
        )
        # Don't fail paper creation if snapshot fails
        return None


def _extract_materialized_text(paper: ResearchPaper) -> Optional[str]:
    """Extract the text content from a paper for snapshotting."""
    # Try content_json first (structured content)
    if isinstance(paper.content_json, dict):
        # LaTeX mode
        latex_source = paper.content_json.get("latex_source")
        if latex_source:
            return latex_source

        # Rich text mode
        rich_text = paper.content_json.get("rich_text")
        if rich_text:
            return rich_text

    # Fall back to legacy content field
    if paper.content:
        return paper.content

    return None


def _extract_materialized_files(paper: ResearchPaper) -> Optional[Dict[str, str]]:
    """Extract additional LaTeX files from a paper for snapshotting."""
    if not isinstance(paper.latex_files, dict):
        return None

    return {
        name: content
        for name, content in paper.latex_files.items()
        if isinstance(name, str) and isinstance(content, str)
    }


def create_snapshot_for_paper(
    db: Session,
    paper: ResearchPaper,
    creator_id: Optional[UUID] = None,
    snapshot_type: str = "save",
    label: Optional[str] = None,
) -> Optional[DocumentSnapshot]:
    """
    Create a new snapshot for an existing paper.

    This is used for manual saves and other snapshot creation needs.
    """
    try:
        materialized_text = _extract_materialized_text(paper)
        materialized_files = _extract_materialized_files(paper)

        if not materialized_text or not materialized_text.strip():
            return None

        snapshot = add_snapshot_with_retry(
            db,
            paper_id=paper.id,
            yjs_state=b"",
            materialized_text=materialized_text,
            materialized_files=materialized_files,
            snapshot_type=snapshot_type,
            label=label,
            created_by=creator_id,
        )
        db.commit()
        db.refresh(snapshot)

        logger.info(
            "Created %s snapshot for paper %s: seq=%s, len=%s",
            snapshot_type, paper.id, snapshot.sequence_number, snapshot.text_length
        )
        return snapshot

    except Exception as e:
        logger.warning(
            "Failed to create snapshot for paper %s: %s",
            paper.id, str(e)
        )
        return None
