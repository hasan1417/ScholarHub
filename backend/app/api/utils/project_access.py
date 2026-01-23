"""Shared helpers for project access control."""

from __future__ import annotations

from typing import Iterable, Optional, Tuple, Union
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import Project, ProjectMember, ProjectRole, User


def _is_valid_uuid(val: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


def _parse_short_id(url_id: str) -> Optional[str]:
    """
    Extract short_id from a URL identifier.

    Handles formats:
    - "slug-shortid" -> returns shortid (last 8 chars after hyphen)
    - "shortid" -> returns shortid if 8 chars
    """
    if not url_id:
        return None

    # If it's a UUID, not a short_id
    if _is_valid_uuid(url_id):
        return None

    # Short ID is 8 alphanumeric chars at the end
    if len(url_id) == 8 and url_id.isalnum():
        return url_id

    # Check for slug-shortid format
    last_hyphen = url_id.rfind('-')
    if last_hyphen > 0:
        potential_short_id = url_id[last_hyphen + 1:]
        if len(potential_short_id) == 8 and potential_short_id.isalnum():
            return potential_short_id

    return None


def get_project_or_404(db: Session, project_id: Union[UUID, str]) -> Project:
    """
    Get a project by ID, supporting both UUID and slug-shortid formats.

    Accepts:
    - UUID: dec91e73-be21-4819-9aad-421a6bc27ad2
    - slug-shortid: arabic-check-processing-a1b2c3d4
    - shortid only: a1b2c3d4
    """
    project = None

    # Try UUID lookup first
    if isinstance(project_id, UUID) or _is_valid_uuid(str(project_id)):
        try:
            uuid_val = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
            project = db.query(Project).filter(Project.id == uuid_val).first()
        except (ValueError, AttributeError):
            pass

    # Try short_id lookup
    if not project:
        short_id = _parse_short_id(str(project_id))
        if short_id:
            project = db.query(Project).filter(Project.short_id == short_id).first()

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
