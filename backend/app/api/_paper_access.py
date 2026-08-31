from __future__ import annotations

import logging
from typing import Optional
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.paper_member import PaperMember, PaperRole
from app.models.research_paper import ResearchPaper
from app.models.user import User
from app.services.paper_membership_service import ensure_paper_membership_for_project_member

__all__ = ["require_paper_access", "require_paper_editor"]

logger = logging.getLogger(__name__)


def _parse_uuid(value: UUID | str) -> Optional[UUID]:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _parse_short_id(value: UUID | str) -> Optional[str]:
    url_id = str(value)
    if not url_id or _parse_uuid(value) is not None:
        return None
    if len(url_id) == 8 and url_id.isalnum():
        return url_id
    last_hyphen = url_id.rfind("-")
    if last_hyphen > 0:
        short_id = url_id[last_hyphen + 1:]
        if len(short_id) == 8 and short_id.isalnum():
            return short_id
    return None


def _get_paper_or_404(db: Session, paper_id: UUID | str) -> ResearchPaper:
    paper = None
    parsed_id = _parse_uuid(paper_id)
    if parsed_id is not None:
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == parsed_id).first()
    if not paper:
        short_id = _parse_short_id(paper_id)
        if short_id:
            paper = db.query(ResearchPaper).filter(ResearchPaper.short_id == short_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Paper not found")
    return paper


def require_paper_access(
    db: Session, paper_id: UUID | str, user: User
) -> ResearchPaper:
    paper = _get_paper_or_404(db, paper_id)
    if paper.owner_id == user.id:
        return paper

    member = db.query(PaperMember).filter(
        PaperMember.paper_id == paper.id,
        PaperMember.user_id == user.id,
        PaperMember.status == "accepted",
    ).first()
    if not member:
        member = ensure_paper_membership_for_project_member(db, paper, user)
    if not member:
        logger.warning(
            "User %s (ID: %s) attempted unauthorized access to paper %s",
            user.email,
            user.id,
            paper_id,
        )
        raise HTTPException(status_code=403, detail="Access denied")
    if member.status != "accepted":
        logger.warning(
            "User %s (ID: %s) attempted access to paper %s with status: %s",
            user.email,
            user.id,
            paper_id,
            member.status,
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied - invitation not accepted",
        )
    return paper


def require_paper_editor(
    db: Session, paper_id: UUID | str, user: User
) -> ResearchPaper:
    paper = _get_paper_or_404(db, paper_id)
    if paper.owner_id == user.id:
        return paper

    member = db.query(PaperMember).filter(
        PaperMember.paper_id == paper.id,
        PaperMember.user_id == user.id,
        PaperMember.status == "accepted",
    ).first()
    if not member:
        member = ensure_paper_membership_for_project_member(db, paper, user)
    if (
        not member
        or member.status != "accepted"
        or member.role not in {PaperRole.OWNER, PaperRole.ADMIN, PaperRole.EDITOR}
    ):
        logger.warning(
            "User %s (ID: %s) attempted unauthorized edit of paper %s",
            user.email,
            user.id,
            paper_id,
        )
        raise HTTPException(status_code=403, detail="Edit access denied")
    return paper
