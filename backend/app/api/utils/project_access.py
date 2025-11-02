"""Shared helpers for project access control."""

from __future__ import annotations

from typing import Iterable, Optional, Tuple
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Project, ProjectMember, ProjectRole, User


def get_project_or_404(db: Session, project_id: UUID) -> Project:
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def ensure_project_member(
    db: Session,
    project: Project,
    user: User,
    *,
    roles: Optional[Iterable[ProjectRole]] = None,
) -> Tuple[Optional[ProjectMember], ProjectRole]:
    """Validate that the user belongs to the project.

    Returns the membership (if any) and the effective role (owner when creator).
    """

    if project.created_by == user.id:
        # Project creator is treated as an admin with "Owner" label in the UI.
        return None, ProjectRole.ADMIN

    membership = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
            ProjectMember.status == "accepted",
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Project access denied")

    if roles and membership.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions")

    return membership, membership.role


def ensure_project_owner(db: Session, project: Project, user: User) -> None:
    if project.created_by == user.id:
        return

    membership = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
            ProjectMember.role == ProjectRole.ADMIN,
            ProjectMember.status == "accepted",
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
