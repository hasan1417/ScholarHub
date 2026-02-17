from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Union
from uuid import UUID, uuid4

import asyncio
import json
import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
    Response,
    WebSocket,
    WebSocketDisconnect,
    BackgroundTasks,
)
from fastapi.responses import StreamingResponse
from sqlalchemy import func
from sqlalchemy.orm import Session, joinedload

from app.api.deps import get_current_user, get_current_verified_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.core.security import verify_token
from app.database import SessionLocal, get_db
from app.models import (
    Meeting,
    ProjectDiscussionChannel,
    ProjectDiscussionChannelResource,
    ProjectDiscussionMessage,
    ProjectDiscussionResourceType,
    ProjectDiscussionTask,
    ProjectDiscussionTaskStatus,
    ProjectDiscussionAssistantExchange,
    ProjectReference,
    Reference,
    ProjectRole,
    ResearchPaper,
    User,
)
from app.schemas.project_discussion import (
    DiscussionAssistantRequest,
    DiscussionAssistantResponse,
    DiscussionAssistantExchangeResponse,
    DiscussionChannelCreate,
    DiscussionChannelResourceCreate,
    DiscussionChannelResourceResponse,
    DiscussionChannelSummary,
    DiscussionChannelUpdate,
    DiscussionMessageCreate,
    DiscussionMessageResponse,
    DiscussionMessageUpdate,
    DiscussionStats,
    DiscussionTaskCreate,
    DiscussionTaskResponse,
    DiscussionTaskUpdate,
    DiscussionThreadResponse,
    OpenRouterModelInfo,
    OpenRouterModelListResponse,
)
from app.core.config import settings
from app.services.ai_service import AIService
from app.services.discussion_ai.openrouter_orchestrator import (
    OpenRouterOrchestrator,
    get_available_models_with_meta,
)
from app.api.utils.openrouter_access import resolve_openrouter_key_for_project
from app.api.utils.request_dedup import check_and_set_request
from app.services.websocket_manager import connection_manager
from app.services.subscription_service import SubscriptionService
from app.api.v1.discussion_helpers import (
    slugify as _slugify,
    build_ai_response as _build_ai_response,
    generate_unique_slug as _generate_unique_slug,
    ensure_default_channel as _ensure_default_channel,
    get_channel_or_404 as _get_channel_or_404,
    serialize_message as _serialize_message,
    serialize_channel as _serialize_channel,
    serialize_resource as _serialize_resource,
    serialize_task as _serialize_task,
    parse_task_status as _parse_task_status,
    discussion_session_id as _discussion_session_id,
    display_name_for_user as _display_name_for_user,
    build_assistant_author_payload as _build_assistant_author_payload,
    broadcast_discussion_event as _broadcast_discussion_event,
    persist_assistant_exchange as _persist_assistant_exchange,
)

router = APIRouter()

logger = logging.getLogger(__name__)

_discussion_ai_core = AIService()


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

    parent_message: Optional[ProjectDiscussionMessage] = None
    channel: Optional[ProjectDiscussionChannel] = None

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


@router.websocket("/projects/{project_id}/discussion/channels/{channel_id}/ws")
async def discussion_channel_ws(
    websocket: WebSocket,
    project_id: str,
    channel_id: UUID,
    token: str = Query(..., description="Bearer token for authentication"),
):
    if not token:
        await websocket.close(code=1008)
        return

    try:
        user_email = verify_token(token)
        if not user_email:
            await websocket.close(code=1008)
            return
    except Exception:
        await websocket.close(code=1008)
        return

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == user_email).first()
        if not user:
            await websocket.close(code=1008)
            return

        project = get_project_or_404(db, project_id)
        ensure_project_member(db, project, user)
        _get_channel_or_404(db, project, channel_id)

        display_name = _display_name_for_user(user)

        user_info = {
            "user_id": str(user.id),
            "name": display_name,
            "email": user.email or "",
        }
    except HTTPException:
        await websocket.close(code=1008)
        return
    except Exception:
        await websocket.close(code=1011)
        return
    finally:
        db.close()

    session_key = _discussion_session_id(project_id, channel_id)
    connection_id: Optional[str] = None

    try:
        connection_id = await connection_manager.connect(websocket, session_key, user_info)
        while True:
            try:
                await websocket.receive_text()
            except WebSocketDisconnect:
                break
            except Exception:
                logger.exception("Error receiving discussion websocket message")
                break
    finally:
        if connection_id:
            try:
                await connection_manager.disconnect(connection_id)
            except Exception:
                logger.exception("Failed to disconnect discussion websocket connection")


@router.get("/projects/{project_id}/discussion/stats")
def get_discussion_stats(
    project_id: str,
    channel_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionStats:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    if channel_id:
        channel = _get_channel_or_404(db, project, channel_id)
    else:
        channel = None

    query = db.query(ProjectDiscussionMessage).filter(ProjectDiscussionMessage.project_id == project.id)
    if channel:
        query = query.filter(ProjectDiscussionMessage.channel_id == channel.id)

    total_messages = query.count()

    thread_query = query.filter(ProjectDiscussionMessage.parent_id.is_(None))
    total_threads = thread_query.count()

    return DiscussionStats(
        project_id=project.id,
        total_messages=total_messages,
        total_threads=total_threads,
        channel_id=channel.id if channel else None,
    )


@router.get("/projects/{project_id}/discussion/channels")
def list_discussion_channels(
    project_id: str,
    include_archived: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DiscussionChannelSummary]:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    _ensure_default_channel(db, project)

    channel_query = db.query(ProjectDiscussionChannel).filter(ProjectDiscussionChannel.project_id == project.id)
    if not include_archived:
        channel_query = channel_query.filter(ProjectDiscussionChannel.is_archived.is_(False))

    channels = channel_query.order_by(ProjectDiscussionChannel.is_default.desc(), ProjectDiscussionChannel.created_at.asc()).all()

    message_counts = (
        db.query(
            ProjectDiscussionMessage.channel_id,
            func.count(ProjectDiscussionMessage.id).label("total_messages"),
        )
        .filter(ProjectDiscussionMessage.project_id == project.id)
        .group_by(ProjectDiscussionMessage.channel_id)
        .all()
    )
    thread_counts = (
        db.query(
            ProjectDiscussionMessage.channel_id,
            func.count(ProjectDiscussionMessage.id).label("total_threads"),
        )
        .filter(
            ProjectDiscussionMessage.project_id == project.id,
            ProjectDiscussionMessage.parent_id.is_(None),
        )
        .group_by(ProjectDiscussionMessage.channel_id)
        .all()
    )

    stats_map: Dict[UUID, Dict[str, int]] = {}
    for channel_id_value, total_messages in message_counts:
        stats_map[channel_id_value] = {"total_messages": total_messages, "total_threads": 0}
    for channel_id_value, total_threads in thread_counts:
        stats_map.setdefault(channel_id_value, {"total_messages": 0, "total_threads": 0})
        stats_map[channel_id_value]["total_threads"] = total_threads

    return [_serialize_channel(channel, stats_map) for channel in channels]


@router.post("/projects/{project_id}/discussion/channels", status_code=status.HTTP_201_CREATED)
def create_discussion_channel(
    project_id: str,
    payload: DiscussionChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionChannelSummary:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    # Check for duplicate channel name
    channel_name = payload.name.strip()
    existing_channel = (
        db.query(ProjectDiscussionChannel)
        .filter(
            ProjectDiscussionChannel.project_id == project.id,
            ProjectDiscussionChannel.name == channel_name,
        )
        .first()
    )
    if existing_channel:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A channel named '{channel_name}' already exists in this project.",
        )

    base_slug = _slugify(payload.slug or payload.name)
    slug = _generate_unique_slug(db, project.id, base_slug)

    # Convert scope to dict for JSONB storage
    scope_dict = None
    if payload.scope and not payload.scope.is_empty():
        scope_dict = {
            "paper_ids": [str(pid) for pid in payload.scope.paper_ids] if payload.scope.paper_ids else None,
            "reference_ids": [str(rid) for rid in payload.scope.reference_ids] if payload.scope.reference_ids else None,
            "meeting_ids": [str(mid) for mid in payload.scope.meeting_ids] if payload.scope.meeting_ids else None,
        }

    channel = ProjectDiscussionChannel(
        project_id=project.id,
        name=payload.name.strip(),
        slug=slug,
        description=payload.description,
        scope=scope_dict,  # null = project-wide, or specific resource IDs
        created_by=current_user.id,
        updated_by=current_user.id,
    )

    db.add(channel)
    db.commit()
    db.refresh(channel)

    return _serialize_channel(channel)


@router.put("/projects/{project_id}/discussion/channels/{channel_id}")
def update_discussion_channel(
    project_id: str,
    channel_id: UUID,
    payload: DiscussionChannelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionChannelSummary:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])
    channel = _get_channel_or_404(db, project, channel_id)

    if payload.name:
        new_name = payload.name.strip()
        # Check for duplicate channel name (excluding current channel)
        existing_channel = (
            db.query(ProjectDiscussionChannel)
            .filter(
                ProjectDiscussionChannel.project_id == project.id,
                ProjectDiscussionChannel.name == new_name,
                ProjectDiscussionChannel.id != channel.id,
            )
            .first()
        )
        if existing_channel:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"A channel named '{new_name}' already exists in this project.",
            )
        channel.name = new_name
    if payload.description is not None:
        channel.description = payload.description
    if payload.is_archived is not None and not channel.is_default:
        channel.is_archived = payload.is_archived
    if payload.scope is not None:
        # Empty scope or all-empty lists means project-wide (set to null in DB)
        if payload.scope.is_empty():
            channel.scope = None
        else:
            channel.scope = {
                "paper_ids": [str(pid) for pid in payload.scope.paper_ids] if payload.scope.paper_ids else None,
                "reference_ids": [str(rid) for rid in payload.scope.reference_ids] if payload.scope.reference_ids else None,
                "meeting_ids": [str(mid) for mid in payload.scope.meeting_ids] if payload.scope.meeting_ids else None,
            }

    channel.updated_by = current_user.id

    db.commit()
    db.refresh(channel)

    return _serialize_channel(channel)


@router.delete("/projects/{project_id}/discussion/channels/{channel_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_discussion_channel(
    project_id: str,
    channel_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a discussion channel and all its contents (messages, tasks, artifacts, etc.)."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])
    channel = _get_channel_or_404(db, project, channel_id)

    if channel.is_default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete the default channel"
        )

    logger.info(
        "Deleting channel: channel_id=%s channel_name=%s project_id=%s by user_id=%s",
        channel.id, channel.name, project.id, current_user.id
    )

    db.delete(channel)
    db.commit()

    return None


@router.get("/projects/{project_id}/discussion/channels/{channel_id}/resources")
def list_channel_resources(
    project_id: str,
    channel_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DiscussionChannelResourceResponse]:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    channel = _get_channel_or_404(db, project, channel_id)

    resources = (
        db.query(ProjectDiscussionChannelResource)
        .options(
            joinedload(ProjectDiscussionChannelResource.paper),
            joinedload(ProjectDiscussionChannelResource.reference),
            joinedload(ProjectDiscussionChannelResource.meeting),
        )
        .filter(ProjectDiscussionChannelResource.channel_id == channel.id)
        .order_by(ProjectDiscussionChannelResource.created_at.desc())
        .all()
    )

    return [_serialize_resource(resource) for resource in resources]


@router.post("/projects/{project_id}/discussion/channels/{channel_id}/resources", status_code=status.HTTP_201_CREATED)
def create_channel_resource(
    project_id: str,
    channel_id: UUID,
    payload: DiscussionChannelResourceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionChannelResourceResponse:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])
    channel = _get_channel_or_404(db, project, channel_id)

    resource_type = ProjectDiscussionResourceType(payload.resource_type)
    resource_details: Dict[str, Any] = dict(payload.details or {})

    if resource_type == ProjectDiscussionResourceType.PAPER:
        paper = (
            db.query(ResearchPaper)
            .filter(
                ResearchPaper.id == payload.paper_id,
                ResearchPaper.project_id == project.id,
            )
            .first()
        )
        if not paper:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Paper not found in project")
        resource_details.update({"title": paper.title})
        if paper.summary:
            resource_details["summary"] = paper.summary
        elif paper.abstract:
            resource_details["summary"] = paper.abstract
        if paper.status:
            resource_details["status"] = paper.status
        if paper.authors:
            resource_details["authors"] = list(paper.authors)
        if paper.year:
            resource_details["year"] = paper.year
    elif resource_type == ProjectDiscussionResourceType.REFERENCE:
        reference_link = (
            db.query(ProjectReference)
            .filter(
                ProjectReference.project_id == project.id,
                ProjectReference.reference_id == payload.reference_id,
            )
            .first()
        )
        if not reference_link:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not linked to project")
        reference_obj = (
            db.query(Reference)
            .filter(Reference.id == payload.reference_id)
            .first()
        )
        if reference_obj:
            resource_details.update({"title": reference_obj.title})
            if reference_obj.summary:
                resource_details["summary"] = reference_obj.summary
            elif reference_obj.abstract:
                resource_details["summary"] = reference_obj.abstract
            if reference_obj.authors:
                resource_details["authors"] = list(reference_obj.authors)
            if reference_obj.year:
                resource_details["year"] = reference_obj.year
            if reference_obj.source:
                resource_details["source"] = reference_obj.source
            if reference_obj.doi:
                resource_details["doi"] = reference_obj.doi
            if reference_obj.url:
                resource_details["url"] = reference_obj.url
        resource_details["project_reference_id"] = str(reference_link.id)
    elif resource_type == ProjectDiscussionResourceType.MEETING:
        meeting = (
            db.query(Meeting)
            .filter(
                Meeting.id == payload.meeting_id,
                Meeting.project_id == project.id,
            )
            .first()
        )
        if not meeting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Meeting not found in project")
        status_value = meeting.status.value if hasattr(meeting.status, "value") else meeting.status
        resource_details.setdefault("status", status_value)
        resource_details.setdefault("has_transcript", bool(meeting.transcript))
        if meeting.summary:
            resource_details["summary"] = meeting.summary
        if meeting.created_at:
            resource_details["created_at"] = meeting.created_at.isoformat()
        if "title" not in resource_details:
            if meeting.summary:
                resource_details["title"] = meeting.summary
            elif meeting.created_at:
                resource_details["title"] = f"Meeting on {meeting.created_at.strftime('%Y-%m-%d')}"
            else:
                resource_details["title"] = "Meeting"

    existing = (
        db.query(ProjectDiscussionChannelResource)
        .filter(
            ProjectDiscussionChannelResource.channel_id == channel.id,
            ProjectDiscussionChannelResource.resource_type == resource_type,
            ProjectDiscussionChannelResource.paper_id == payload.paper_id,
            ProjectDiscussionChannelResource.reference_id == payload.reference_id,
            ProjectDiscussionChannelResource.meeting_id == payload.meeting_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Resource already linked to channel")

    resource = ProjectDiscussionChannelResource(
        channel_id=channel.id,
        resource_type=resource_type,
        paper_id=payload.paper_id,
        reference_id=payload.reference_id,
        meeting_id=payload.meeting_id,
        details=resource_details,
        added_by=current_user.id,
    )

    db.add(resource)
    db.commit()
    db.refresh(resource)

    return _serialize_resource(resource)


@router.delete("/projects/{project_id}/discussion/channels/{channel_id}/resources/{resource_id}")
def delete_channel_resource(
    project_id: str,
    channel_id: UUID,
    resource_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])
    _get_channel_or_404(db, project, channel_id)

    resource = (
        db.query(ProjectDiscussionChannelResource)
        .filter(
            ProjectDiscussionChannelResource.id == resource_id,
            ProjectDiscussionChannelResource.channel_id == channel_id,
        )
        .first()
    )
    if not resource:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")

    db.delete(resource)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/projects/{project_id}/discussion/models")
def list_openrouter_models(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    include_meta: bool = Query(False),
) -> Union[List[OpenRouterModelInfo], OpenRouterModelListResponse]:
    """List available OpenRouter models."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    discussion_settings = project.discussion_settings or {"enabled": True, "model": "openai/gpt-5.2-20251211"}
    use_owner_key_for_team = bool(discussion_settings.get("use_owner_key_for_team", False))
    resolution = resolve_openrouter_key_for_project(
        db,
        current_user,
        project,
        use_owner_key_for_team=use_owner_key_for_team,
    )

    meta = get_available_models_with_meta(
        include_reasoning=True,
        require_tools=True,
        api_key=resolution.get("api_key"),
        use_env_key=False,
    )
    models = [OpenRouterModelInfo(**m) for m in meta["models"]]
    warning = resolution.get("warning") or meta.get("warning")

    if include_meta:
        return OpenRouterModelListResponse(
            models=models,
            source=meta.get("source") or "fallback",
            warning=warning,
            key_source=resolution.get("source") or "none",
        )

    return models


@router.post(
    "/projects/{project_id}/discussion/channels/{channel_id}/assistant",
    response_model=DiscussionAssistantResponse,
)
async def invoke_discussion_assistant(
    project_id: str,
    channel_id: UUID,
    payload: DiscussionAssistantRequest,
    background_tasks: BackgroundTasks,
    stream: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_verified_user),
):
    """
    Invoke the AI assistant using OpenRouter.

    Model and API key are determined by project settings:
    - Model: from project.discussion_settings.model
    - API Key: project owner's key (fallback to current user's key)
    """
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    channel = _get_channel_or_404(db, project, channel_id)

    # Get discussion settings from project
    discussion_settings = project.discussion_settings or {"enabled": True, "model": "openai/gpt-5.2-20251211"}

    # Check if discussion AI is enabled for this project
    if not discussion_settings.get("enabled", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Discussion AI is disabled for this project",
        )

    # Use model from project settings
    model = discussion_settings.get("model", "openai/gpt-5.2-20251211")

    # Determine API key based on user tier + project settings
    use_owner_key_for_team = bool(discussion_settings.get("use_owner_key_for_team", False))
    resolution = resolve_openrouter_key_for_project(
        db,
        current_user,
        project,
        use_owner_key_for_team=use_owner_key_for_team,
    )
    api_key_to_use = resolution.get("api_key")
    key_source = resolution.get("source") or "none"

    if resolution.get("error_status"):
        raise HTTPException(
            status_code=int(resolution["error_status"]),
            detail={
                "error": "no_api_key" if resolution["error_status"] == 402 else "invalid_api_key",
                "message": resolution.get("error_detail") or "OpenRouter API key issue.",
            },
        )

    if not api_key_to_use:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "no_api_key",
                "message": "No API key available. Add your OpenRouter key or ask the project owner to enable key sharing.",
            },
        )

    logger.info(f"Using {key_source} OpenRouter API key for Discussion AI")

    # Check discussion AI credit limit (premium models cost 5, standard cost 1)
    from app.services.subscription_service import get_model_credit_cost
    credit_cost = get_model_credit_cost(model)
    allowed, current_usage, limit = SubscriptionService.check_feature_limit(
        db, current_user.id, "discussion_ai_calls"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "discussion_ai_calls",
                "current": current_usage,
                "limit": limit,
                "message": f"You have reached your discussion AI credit limit ({current_usage}/{limit} credits this month). Upgrade to Pro for more credits.",
            },
        )

    display_name = _display_name_for_user(current_user)
    author_info = {
        "id": str(current_user.id),
        "name": {
            "first": current_user.first_name or "",
            "last": current_user.last_name or "",
            "display": display_name,
        },
    }
    logger.info(f"AI Assistant - User: {current_user.email}, model: {model} (from project settings)")

    # M2 Security Fix: Fetch search results from server cache instead of trusting client data
    from app.services.discussion_ai.search_cache import get_search_results

    search_results_list = None
    if payload.recent_search_id:
        search_results_list = get_search_results(payload.recent_search_id)
        if search_results_list:
            logger.info(f"AI Assistant - Loaded {len(search_results_list)} papers from server cache (search_id={payload.recent_search_id})")
        else:
            logger.warning(f"AI Assistant - No cached results for search_id={payload.recent_search_id}, ignoring client data")

    if payload.recent_search_results and not search_results_list:
        logger.info(f"AI Assistant - Ignoring {len(payload.recent_search_results)} client-provided search results (not in server cache)")

    # Load previous conversation state
    previous_state_dict = None
    last_exchange = (
        db.query(ProjectDiscussionAssistantExchange)
        .filter(
            ProjectDiscussionAssistantExchange.project_id == project.id,
            ProjectDiscussionAssistantExchange.channel_id == channel.id,
        )
        .order_by(ProjectDiscussionAssistantExchange.created_at.desc())
        .first()
    )
    if last_exchange and last_exchange.conversation_state:
        previous_state_dict = last_exchange.conversation_state

    # Create OpenRouter orchestrator with the determined API key
    orchestrator = OpenRouterOrchestrator(
        _discussion_ai_core,
        db,
        model=model,
        user_api_key=api_key_to_use,
    )

    # Convert conversation history if provided
    conversation_history = None
    if payload.conversation_history:
        conversation_history = [
            {"role": h.role, "content": h.content}
            for h in payload.conversation_history
        ]

    # Use streaming if requested
    if stream:
        exchange_id = str(uuid4())
        exchange_created_at = datetime.utcnow().isoformat() + "Z"

        # Check for duplicate request using idempotency key
        if payload.idempotency_key:
            is_new, existing_exchange_id = check_and_set_request(
                payload.idempotency_key,
                exchange_id,
            )
            if not is_new and existing_exchange_id:
                logger.info(f"Duplicate request detected, returning existing exchange: {existing_exchange_id}")
                async def duplicate_response():
                    yield f"data: {json.dumps({'type': 'duplicate', 'exchange_id': existing_exchange_id})}\n\n"
                return StreamingResponse(
                    duplicate_response(),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "Connection": "keep-alive",
                        "X-Duplicate-Request": "true",
                        "X-Existing-Exchange-Id": existing_exchange_id,
                    },
                )

        # Save exchange immediately with status="processing"
        initial_response = DiscussionAssistantResponse(
            message="",
            citations=[],
            reasoning_used=False,
            model=model,
            usage=None,
            suggested_actions=[],
        )
        await asyncio.to_thread(
            _persist_assistant_exchange,
            project.id,
            channel.id,
            current_user.id,
            exchange_id,
            payload.question,
            initial_response.model_dump(mode="json"),
            exchange_created_at,
            {},
            "processing",
            "Thinking",
        )
        await _broadcast_discussion_event(
            project.id,
            channel.id,
            "assistant_processing",
            {"exchange": {
                "id": exchange_id,
                "question": payload.question,
                "status": "processing",
                "status_message": "Thinking",
                "created_at": exchange_created_at,
                "author": author_info,
            }},
        )

        # Capture values for the async generator closure
        proj_id = project.id
        chan_id = channel.id
        user_id = current_user.id
        question_text = payload.question
        reasoning_enabled = payload.reasoning or False
        selected_model = model

        async def stream_sse():
            """Async generator that streams SSE events from the orchestrator."""
            try:
                final_result = None
                async for event in orchestrator.handle_message_streaming(
                    project,
                    channel,
                    question_text,
                    recent_search_results=search_results_list,
                    recent_search_id=payload.recent_search_id,
                    previous_state_dict=previous_state_dict,
                    conversation_history=conversation_history,
                    reasoning_mode=reasoning_enabled,
                    current_user=current_user,
                ):
                    if event.get("type") == "token":
                        yield "data: " + json.dumps({"type": "token", "content": event.get("content", "")}) + "\n\n"
                    elif event.get("type") == "status":
                        status_msg = event.get("message", "Processing...")
                        # Update status in DB and broadcast
                        try:
                            def _update_status():
                                sdb = SessionLocal()
                                try:
                                    rec = sdb.query(ProjectDiscussionAssistantExchange).filter_by(
                                        id=UUID(exchange_id)
                                    ).first()
                                    if rec:
                                        rec.status_message = status_msg
                                        sdb.commit()
                                finally:
                                    sdb.close()
                            await asyncio.to_thread(_update_status)
                            await _broadcast_discussion_event(
                                proj_id, chan_id, "assistant_status",
                                {"exchange_id": exchange_id, "status_message": status_msg},
                            )
                        except Exception as e:
                            logger.warning(f"Failed to update status message: {e}")
                        yield "data: " + json.dumps({"type": "status", "tool": event.get("tool", ""), "message": status_msg}) + "\n\n"
                    elif event.get("type") == "content_reset":
                        yield "data: " + json.dumps({"type": "content_reset"}) + "\n\n"
                    elif event.get("type") == "result":
                        final_result = event.get("data", {})
                        response_model = _build_ai_response(final_result, selected_model)
                        yield "data: " + json.dumps({"type": "result", "payload": response_model.model_dump(mode="json")}) + "\n\n"
                    elif event.get("type") == "error":
                        yield "data: " + json.dumps({"type": "error", "message": event.get("message", "Error")}) + "\n\n"

                # Fire-and-forget: persist + broadcast in background so the stream closes immediately
                if final_result:
                    _final = final_result

                    async def _post_stream_work():
                        try:
                            resp = _build_ai_response(_final, selected_model)
                            pdict = resp.model_dump(mode="json")
                            cstate = _final.get("conversation_state", {})
                            await asyncio.to_thread(
                                _persist_assistant_exchange,
                                proj_id, chan_id, user_id, exchange_id,
                                question_text, pdict, exchange_created_at,
                                cstate, "completed",
                            )
                            await _broadcast_discussion_event(
                                proj_id, chan_id, "assistant_reply",
                                {"exchange": {
                                    "id": exchange_id,
                                    "question": question_text,
                                    "response": pdict,
                                    "created_at": exchange_created_at,
                                    "author": author_info,
                                    "status": "completed",
                                }},
                            )
                            await asyncio.to_thread(SubscriptionService.increment_usage, db, user_id, "discussion_ai_calls", credit_cost)
                        except Exception as e:
                            logger.error(f"Post-stream work failed for exchange {exchange_id}: {e}")

                    asyncio.create_task(_post_stream_work())

            except GeneratorExit:
                logger.info(f"Client disconnected during streaming for exchange {exchange_id}")
                # Mark exchange as failed so it doesn't stay stuck in "processing" forever.
                # _persist_assistant_exchange is sync (uses its own SessionLocal), so no await needed.
                try:
                    _persist_assistant_exchange(
                        proj_id, chan_id, user_id, exchange_id,
                        question_text,
                        {"message": "Response interrupted — you navigated away before it completed. Please try again.",
                         "citations": [], "suggested_actions": []},
                        exchange_created_at, {}, "failed",
                        "Client disconnected",
                    )
                except Exception:
                    logger.warning(f"Failed to mark exchange {exchange_id} as failed after client disconnect")
            except Exception as exc:
                logger.exception("Streaming error", exc_info=exc)
                await asyncio.to_thread(
                    _persist_assistant_exchange,
                    proj_id, chan_id, user_id, exchange_id,
                    question_text,
                    {"message": "An error occurred while processing your request.", "citations": [], "suggested_actions": []},
                    exchange_created_at, {}, "failed",
                    "Processing failed. Please try again.",
                )
                await _broadcast_discussion_event(
                    proj_id, chan_id, "assistant_failed",
                    {"exchange_id": exchange_id, "error": "Processing failed"},
                )
                yield "data: " + json.dumps({"type": "error", "message": "Processing failed"}) + "\n\n"

        return StreamingResponse(
            stream_sse(),
            media_type="text/event-stream",
            headers={"X-Exchange-Id": exchange_id},
        )

    # Non-streaming mode
    result = orchestrator.handle_message(
        project,
        channel,
        payload.question,
        recent_search_results=search_results_list,
        recent_search_id=payload.recent_search_id,
        previous_state_dict=previous_state_dict,
        conversation_history=conversation_history,
        reasoning_mode=payload.reasoning or False,
        current_user=current_user,
    )

    response = _build_ai_response(result, model)

    # Persist exchange
    exchange_id = str(uuid4())
    exchange_created_at = datetime.utcnow().isoformat() + "Z"
    _persist_assistant_exchange(
        project.id,
        channel.id,
        current_user.id,
        exchange_id,
        payload.question,
        response.model_dump(mode="json"),
        exchange_created_at,
        result.get("conversation_state", {}),
        status="completed",
    )

    # Increment discussion AI credits
    try:
        SubscriptionService.increment_usage(db, current_user.id, "discussion_ai_calls", amount=credit_cost)
    except Exception as e:
        logger.error(f"Failed to increment discussion AI usage for user {current_user.id}: {e}")

    return response


@router.get(
    "/projects/{project_id}/discussion/channels/{channel_id}/assistant-history",
    response_model=List[DiscussionAssistantExchangeResponse],
)
def list_discussion_assistant_history(
    project_id: str,
    channel_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    channel = _get_channel_or_404(db, project, channel_id)

    exchanges = (
        db.query(ProjectDiscussionAssistantExchange)
        .options(joinedload(ProjectDiscussionAssistantExchange.author))
        .filter(
            ProjectDiscussionAssistantExchange.project_id == project.id,
            ProjectDiscussionAssistantExchange.channel_id == channel.id,
        )
        .order_by(ProjectDiscussionAssistantExchange.created_at.asc())
        .all()
    )

    # Auto-expire exchanges stuck in "processing" for over 2 minutes
    stale_cutoff = datetime.utcnow() - timedelta(minutes=2)
    for exchange in exchanges:
        if (
            getattr(exchange, "status", None) == "processing"
            and exchange.created_at
            and exchange.created_at < stale_cutoff
        ):
            exchange.status = "failed"
            exchange.status_message = "Request timed out"
            exchange.response = {
                "message": "This request timed out or was interrupted. Please try again.",
                "citations": [],
                "suggested_actions": [],
                "model": exchange.response.get("model", "") if isinstance(exchange.response, dict) else "",
            }
            db.commit()

    results: List[DiscussionAssistantExchangeResponse] = []
    for exchange in exchanges:
        try:
            response_payload = DiscussionAssistantResponse(**exchange.response)
        except Exception:
            # Fallback to basic structure if stored payload is malformed
            response_payload = _build_ai_response(
                exchange.response, str(exchange.response.get("model", ""))
            )

        author_payload = _build_assistant_author_payload(exchange.author)

        results.append(
            DiscussionAssistantExchangeResponse(
                id=exchange.id,
                question=exchange.question,
                response=response_payload,
                created_at=exchange.created_at or datetime.utcnow(),
                author=author_payload,
                status=getattr(exchange, 'status', 'completed') or 'completed',
                status_message=getattr(exchange, 'status_message', None),
            )
        )

    return results


@router.get("/projects/{project_id}/discussion/tasks")
def list_discussion_tasks(
    project_id: str,
    channel_id: Optional[UUID] = None,
    status_filter: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[DiscussionTaskResponse]:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    status_enum = _parse_task_status(status_filter)

    query = db.query(ProjectDiscussionTask).filter(ProjectDiscussionTask.project_id == project.id)
    if channel_id:
        _get_channel_or_404(db, project, channel_id)
        query = query.filter(ProjectDiscussionTask.channel_id == channel_id)
    if status_enum:
        query = query.filter(ProjectDiscussionTask.status == status_enum)

    tasks = query.order_by(ProjectDiscussionTask.created_at.desc()).all()
    return [_serialize_task(task) for task in tasks]


@router.post("/projects/{project_id}/discussion/channels/{channel_id}/tasks", status_code=status.HTTP_201_CREATED)
def create_discussion_task(
    project_id: str,
    channel_id: UUID,
    payload: DiscussionTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionTaskResponse:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])
    channel = _get_channel_or_404(db, project, channel_id)

    if payload.message_id:
        message = (
            db.query(ProjectDiscussionMessage)
            .filter(
                ProjectDiscussionMessage.id == payload.message_id,
                ProjectDiscussionMessage.project_id == project.id,
            )
            .first()
        )
        if not message:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        if message.channel_id != channel.id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message does not belong to channel")

    task = ProjectDiscussionTask(
        project_id=project.id,
        channel_id=channel.id,
        message_id=payload.message_id,
        title=payload.title.strip(),
        description=payload.description,
        assignee_id=payload.assignee_id,
        due_date=payload.due_date,
        details=payload.details,
        created_by=current_user.id,
        updated_by=current_user.id,
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return _serialize_task(task)


@router.put("/projects/{project_id}/discussion/tasks/{task_id}")
def update_discussion_task(
    project_id: str,
    task_id: UUID,
    payload: DiscussionTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionTaskResponse:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    task = (
        db.query(ProjectDiscussionTask)
        .filter(
            ProjectDiscussionTask.id == task_id,
            ProjectDiscussionTask.project_id == project.id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    if payload.title:
        task.title = payload.title.strip()
    if payload.description is not None:
        task.description = payload.description
    if payload.assignee_id is not None:
        task.assignee_id = payload.assignee_id
    if payload.due_date is not None:
        task.due_date = payload.due_date
    if payload.details is not None:
        task.details = payload.details
    if payload.status is not None:
        task.status = _parse_task_status(payload.status)
        if task.status == ProjectDiscussionTaskStatus.COMPLETED:
            task.completed_at = datetime.now(timezone.utc)
        elif task.status in {ProjectDiscussionTaskStatus.OPEN, ProjectDiscussionTaskStatus.IN_PROGRESS}:
            task.completed_at = None

    task.updated_by = current_user.id

    db.commit()
    db.refresh(task)

    return _serialize_task(task)


@router.delete("/projects/{project_id}/discussion/tasks/{task_id}")
def delete_discussion_task(
    project_id: str,
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    task = (
        db.query(ProjectDiscussionTask)
        .filter(
            ProjectDiscussionTask.id == task_id,
            ProjectDiscussionTask.project_id == project.id,
        )
        .first()
    )
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")

    db.delete(task)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
