"""
Paper Service - Centralized paper creation and management.

All paper creation should go through this service to ensure:
- Consistent paper structure
- Initial snapshot creation for version history
- Proper member/owner setup
"""
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.research_paper import ResearchPaper
from app.models.paper_member import PaperMember, PaperRole
from app.models.document_snapshot import DocumentSnapshot
from app.models.user import User
from app.models.project import Project

logger = logging.getLogger(__name__)


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

        if not materialized_text or not materialized_text.strip():
            logger.debug("No content to snapshot for paper %s", paper.id)
            return None

        snapshot = DocumentSnapshot(
            paper_id=paper.id,
            yjs_state=b"",  # No Yjs state for API-created papers
            materialized_text=materialized_text,
            snapshot_type="auto",
            label=label,
            created_by=creator_id,
            sequence_number=1,
            text_length=len(materialized_text),
        )
        db.add(snapshot)
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
    from sqlalchemy import func

    try:
        materialized_text = _extract_materialized_text(paper)

        if not materialized_text or not materialized_text.strip():
            return None

        # Get next sequence number
        max_seq = db.query(func.max(DocumentSnapshot.sequence_number)).filter(
            DocumentSnapshot.paper_id == paper.id
        ).scalar()
        next_seq = (max_seq or 0) + 1

        snapshot = DocumentSnapshot(
            paper_id=paper.id,
            yjs_state=b"",
            materialized_text=materialized_text,
            snapshot_type=snapshot_type,
            label=label,
            created_by=creator_id,
            sequence_number=next_seq,
            text_length=len(materialized_text),
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)

        logger.info(
            "Created %s snapshot for paper %s: seq=%s, len=%s",
            snapshot_type, paper.id, next_seq, snapshot.text_length
        )
        return snapshot

    except Exception as e:
        logger.warning(
            "Failed to create snapshot for paper %s: %s",
            paper.id, str(e)
        )
        return None
