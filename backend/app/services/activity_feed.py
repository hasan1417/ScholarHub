from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Notification, Project, ProjectMember, User


def _display_name(user: Optional[User]) -> str:
    if not user:
        return "Unknown user"
    parts = [part.strip() for part in [user.first_name or "", user.last_name or ""] if part]
    if parts:
        return " ".join(parts)
    return user.email or "Unknown user"


def preview_text(value: Optional[str], limit: int = 160) -> str:
    if not value:
        return ""
    compact = " ".join(value.strip().split())
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 1, 0)].rstrip() + "…"


def record_project_activity(
    db: Session,
    *,
    project: Project,
    actor: Optional[User],
    event_type: str,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    """Fan out a project notification capturing an activity event.

    Notifications are stored per accepted project member so they can surface in the
    project Updates feed on the frontend. The helper is intentionally resilient; if
    notifications are disabled or the project has no accepted members it simply
    returns without raising.
    """

    if not settings.PROJECT_NOTIFICATIONS_ENABLED:
        return

    members = (
        db.query(ProjectMember)
        .filter(ProjectMember.project_id == project.id, ProjectMember.status == "accepted")
        .all()
    )
    if not members:
        return

    actor_info = {
        "id": str(actor.id) if actor and actor.id else None,
        "name": _display_name(actor),
        "email": actor.email if actor else None,
    }

    base_payload: Dict[str, Any] = {
        "actor": actor_info,
        "project": {
            "id": str(project.id),
            "title": project.title,
        },
        "event_type": event_type,
        "category": event_type.split(".")[0] if "." in event_type else event_type,
        "recorded_at": datetime.utcnow().isoformat() + "Z",
    }
    if payload:
        base_payload.update(payload)

    for member in members:
        notification = Notification(
            user_id=member.user_id,
            project_id=project.id,
            type=event_type,
            payload=dict(base_payload),
        )
        db.add(notification)
