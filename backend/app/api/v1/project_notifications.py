from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.core.config import settings
from app.database import get_db
from app.models import Notification, ProjectRole, User


router = APIRouter()


def _guard_feature() -> None:
    if not settings.PROJECT_NOTIFICATIONS_ENABLED:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notifications disabled")


def _serialize(notification: Notification) -> dict:
    return {
        "id": str(notification.id),
        "user_id": str(notification.user_id),
        "project_id": str(notification.project_id) if notification.project_id else None,
        "type": notification.type,
        "payload": notification.payload,
        "read": notification.read,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
    }


@router.get("/notifications")
def list_notifications(
    project_id: Optional[UUID] = None,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()

    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if project_id:
        query = query.filter(Notification.project_id == project_id)
    if unread_only:
        query = query.filter(Notification.read.is_(False))

    notifications = query.order_by(Notification.created_at.desc()).all()
    return {
        "notifications": [_serialize(item) for item in notifications],
    }


@router.post("/notifications/{notification_id}/read")
def mark_notification_as_read(
    notification_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()

    notification = (
        db.query(Notification)
        .filter(
            Notification.id == notification_id,
            Notification.user_id == current_user.id,
        )
        .first()
    )
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")

    notification.read = True
    db.commit()
    db.refresh(notification)
    return _serialize(notification)


@router.get("/projects/{project_id}/notifications")
def list_project_notifications(
    project_id: UUID,
    unread_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _guard_feature()
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    query = db.query(Notification).filter(Notification.user_id == current_user.id, Notification.project_id == project.id)
    if unread_only:
        query = query.filter(Notification.read.is_(False))

    notifications = query.order_by(Notification.created_at.desc()).all()
    return {
        "project_id": str(project.id),
        "notifications": [_serialize(item) for item in notifications],
    }
