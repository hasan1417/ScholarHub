"""Discussion message endpoints: list, create, update, delete messages and threads."""
from __future__ import annotations

from typing import Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Response, BackgroundTasks
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.database import get_db
from app.models import (
    ProjectDiscussionMessage,
    ProjectRole,
    User,
)
from app.schemas.project_discussion import (
    DiscussionMessageCreate,
    DiscussionMessageResponse,
    DiscussionMessageUpdate,
    DiscussionThreadResponse,
)
from app.api.v1.discussion_helpers import (
    ensure_default_channel as _ensure_default_channel,
    get_channel_or_404 as _get_channel_or_404,
    serialize_message as _serialize_message,
    broadcast_discussion_event as _broadcast_discussion_event,
)

router = APIRouter()


@router.get("/projects/{project_id}/discussion/messages")
def list_discussion_messages(
    project_id: str,
    limit: int = 100,
    offset: int = 0,
    parent_id: Optional[UUID] = None,
    channel_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DiscussionMessageResponse]:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    if channel_id:
        channel = _get_channel_or_404(db, project, channel_id)
    else:
        channel = _ensure_default_channel(db, project)

    query = (
        db.query(ProjectDiscussionMessage)
        .filter(
            ProjectDiscussionMessage.project_id == project.id,
            ProjectDiscussionMessage.channel_id == channel.id,
        )
        .options(
            joinedload(ProjectDiscussionMessage.user),
            joinedload(ProjectDiscussionMessage.attachments),
        )
    )

    if parent_id is not None:
        query = query.filter(ProjectDiscussionMessage.parent_id == parent_id)
    else:
        query = query.filter(ProjectDiscussionMessage.parent_id.is_(None))

    messages = (
        query.order_by(ProjectDiscussionMessage.created_at.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    message_ids = [msg.id for msg in messages]
    reply_counts: Dict[UUID, int] = {}
    if message_ids:
        counts = (
            db.query(
                ProjectDiscussionMessage.parent_id,
                func.count(ProjectDiscussionMessage.id).label("count"),
            )
            .filter(
                ProjectDiscussionMessage.parent_id.in_(message_ids),
                ProjectDiscussionMessage.channel_id == channel.id,
            )
            .group_by(ProjectDiscussionMessage.parent_id)
            .all()
        )
        reply_counts = {parent: count for parent, count in counts}

    return [_serialize_message(msg, reply_counts.get(msg.id, 0)) for msg in messages]


@router.get("/projects/{project_id}/discussion/threads")
def list_discussion_threads(
    project_id: str,
    limit: int = 50,
    offset: int = 0,
    channel_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DiscussionThreadResponse]:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    if channel_id:
        channel = _get_channel_or_404(db, project, channel_id)
    else:
        channel = _ensure_default_channel(db, project)

    top_level_messages = (
        db.query(ProjectDiscussionMessage)
        .filter(
            ProjectDiscussionMessage.project_id == project.id,
            ProjectDiscussionMessage.channel_id == channel.id,
            ProjectDiscussionMessage.parent_id.is_(None),
        )
        .options(
            joinedload(ProjectDiscussionMessage.user),
            joinedload(ProjectDiscussionMessage.attachments),
        )
        .order_by(ProjectDiscussionMessage.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    threads: List[DiscussionThreadResponse] = []
    for message in top_level_messages:
        replies = (
            db.query(ProjectDiscussionMessage)
            .filter(
                ProjectDiscussionMessage.parent_id == message.id,
                ProjectDiscussionMessage.channel_id == channel.id,
            )
            .options(
                joinedload(ProjectDiscussionMessage.user),
                joinedload(ProjectDiscussionMessage.attachments),
            )
            .order_by(ProjectDiscussionMessage.created_at.asc())
            .all()
        )

        threads.append(
            DiscussionThreadResponse(
                message=_serialize_message(message, len(replies)),
                replies=[_serialize_message(reply, 0) for reply in replies],
            )
        )

    return threads


@router.post("/projects/{project_id}/discussion/messages", status_code=status.HTTP_201_CREATED)
def create_discussion_message(
    project_id: str,
    message_data: DiscussionMessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionMessageResponse:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)  # Viewers can chat (AI tools are filtered separately)

    parent_message = None
    channel = None

    if message_data.parent_id:
        parent_message = (
            db.query(ProjectDiscussionMessage)
            .filter(
                ProjectDiscussionMessage.id == message_data.parent_id,
                ProjectDiscussionMessage.project_id == project.id,
            )
            .first()
        )
        if not parent_message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent message not found")
        channel = parent_message.channel
    elif message_data.channel_id:
        channel = _get_channel_or_404(db, project, message_data.channel_id)
    else:
        channel = _ensure_default_channel(db, project)

    message = ProjectDiscussionMessage(
        project_id=project.id,
        channel_id=channel.id,
        user_id=current_user.id,
        content=message_data.content,
        parent_id=message_data.parent_id,
    )

    db.add(message)
    db.commit()
    db.refresh(message, ["user", "attachments"])

    serialized = _serialize_message(message, 0)

    if background_tasks is not None:
        event_payload = {
            "message": serialized.model_dump(mode="json"),
            "parent_id": str(message.parent_id) if message.parent_id else None,
        }
        background_tasks.add_task(
            _broadcast_discussion_event,
            project.id,
            channel.id,
            "message_created",
            event_payload,
        )

    return serialized


@router.put("/projects/{project_id}/discussion/messages/{message_id}")
def update_discussion_message(
    project_id: str,
    message_id: UUID,
    message_data: DiscussionMessageUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionMessageResponse:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)  # Author check below handles permissions

    message = (
        db.query(ProjectDiscussionMessage)
        .filter(
            ProjectDiscussionMessage.id == message_id,
            ProjectDiscussionMessage.project_id == project.id,
        )
        .options(
            joinedload(ProjectDiscussionMessage.user),
            joinedload(ProjectDiscussionMessage.attachments),
        )
        .first()
    )

    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    if message.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You can only edit your own messages")

    if message.is_deleted:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a deleted message")

    message.content = message_data.content
    message.is_edited = True

    db.commit()
    db.refresh(message)

    reply_count = (
        db.query(func.count(ProjectDiscussionMessage.id))
        .filter(
            ProjectDiscussionMessage.parent_id == message.id,
            ProjectDiscussionMessage.channel_id == message.channel_id,
        )
        .scalar()
    )

    serialized = _serialize_message(message, reply_count or 0)

    if background_tasks is not None:
        event_payload = {
            "message": serialized.model_dump(mode="json"),
            "parent_id": str(message.parent_id) if message.parent_id else None,
        }
        background_tasks.add_task(
            _broadcast_discussion_event,
            project.id,
            message.channel_id,
            "message_updated",
            event_payload,
        )

    return serialized


@router.delete("/projects/{project_id}/discussion/messages/{message_id}")
def delete_discussion_message(
    project_id: str,
    message_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    project = get_project_or_404(db, project_id)
    _membership, role = ensure_project_member(db, project, current_user)  # Author/admin check below

    message = (
        db.query(ProjectDiscussionMessage)
        .filter(
            ProjectDiscussionMessage.id == message_id,
            ProjectDiscussionMessage.project_id == project.id,
        )
        .first()
    )

    if not message:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    is_author = message.user_id == current_user.id
    is_admin = role == ProjectRole.ADMIN

    if not (is_author or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own messages or you must be a project admin",
        )

    message.is_deleted = True
    message.content = "[This message has been deleted]"

    channel_id = message.channel_id
    parent_id = message.parent_id

    db.commit()

    if background_tasks is not None:
        event_payload = {
            "message_id": str(message.id),
            "parent_id": str(parent_id) if parent_id else None,
        }
        background_tasks.add_task(
            _broadcast_discussion_event,
            project.id,
            channel_id,
            "message_deleted",
            event_payload,
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)
