from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.models.paper_member import PaperMember, PaperRole
from app.models.project_member import ProjectMember, ProjectRole
from app.models.research_paper import ResearchPaper
from app.models.user import User


def _map_project_role_to_paper_role(project_role: Optional[ProjectRole]) -> PaperRole:
    if project_role in {ProjectRole.OWNER, ProjectRole.ADMIN}:
        return PaperRole.ADMIN
    if project_role == ProjectRole.EDITOR:
        return PaperRole.EDITOR
    return PaperRole.VIEWER


def ensure_paper_membership_for_project_member(
    db: Session, paper: ResearchPaper, user: User
) -> Optional[PaperMember]:
    """
    If the user is an accepted member of the paper's project, ensure they
    also have an accepted PaperMember record (creating or upgrading it).
    Returns the PaperMember when access is granted, otherwise None.
    """
    if not paper.project_id:
        return None

    project_member = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == paper.project_id,
            ProjectMember.user_id == user.id,
            ProjectMember.status == "accepted",
        )
        .first()
    )
    if not project_member:
        return None

    existing_member = (
        db.query(PaperMember)
        .filter(PaperMember.paper_id == paper.id, PaperMember.user_id == user.id)
        .first()
    )

    if existing_member:
        if existing_member.status != "accepted":
            existing_member.status = "accepted"
            existing_member.joined_at = existing_member.joined_at or datetime.utcnow()
            db.commit()
        return existing_member

    paper_member = PaperMember(
        paper_id=paper.id,
        user_id=user.id,
        role=_map_project_role_to_paper_role(project_member.role),
        status="accepted",
        invited_by=paper.owner_id,
        joined_at=datetime.utcnow(),
    )
    db.add(paper_member)
    db.commit()
    db.refresh(paper_member)

    return paper_member
