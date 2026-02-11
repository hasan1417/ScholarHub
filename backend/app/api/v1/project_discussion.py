from __future__ import annotations

import re
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
    PaperMember,
    Project,
    ProjectDiscussionChannel,
    ProjectDiscussionChannelResource,
    ProjectDiscussionMessage,
    ProjectDiscussionMessageAttachment,
    ProjectDiscussionResourceType,
    ProjectDiscussionTask,
    ProjectDiscussionTaskStatus,
    ProjectDiscussionAssistantExchange,
    ProjectReference,
    Reference,
    ProjectRole,
    ResearchPaper,
    User,
    DiscussionArtifact,
)
from pydantic import BaseModel
from app.schemas.project_discussion import (
    DiscussionAssistantCitation,
    DiscussionAssistantRequest,
    DiscussionAssistantResponse,
    DiscussionAssistantExchangeResponse,

    DiscussionChannelCreate,
    DiscussionChannelResourceCreate,
    DiscussionChannelResourceResponse,
    DiscussionChannelSummary,
    DiscussionChannelUpdate,
    DiscussionMessageAttachmentResponse,
    DiscussionMessageCreate,
    DiscussionMessageResponse,
    DiscussionMessageUpdate,
    DiscussionMessageUserInfo,
    DiscussionStats,
    DiscussionTaskCreate,
    DiscussionTaskResponse,
    DiscussionTaskUpdate,
    DiscussionThreadResponse,
)
from app.core.config import settings
from app.services.ai_service import AIService
from app.services.discussion_ai.openrouter_orchestrator import (
    OpenRouterOrchestrator,
    get_available_models_with_meta,
)
from app.api.utils.openrouter_access import resolve_openrouter_key_for_project
from app.api.utils.request_dedup import check_and_set_request, clear_request
from app.services.websocket_manager import connection_manager
from app.services.subscription_service import SubscriptionService

router = APIRouter()

logger = logging.getLogger(__name__)

_discussion_ai_core = AIService()

_slug_regex = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    base = _slug_regex.sub("-", value.lower()).strip("-")
    return base or "channel"


def _build_citations(result_dict: Dict[str, Any]) -> List[DiscussionAssistantCitation]:
    """Build citation objects from an AI result dict."""
    return [
        DiscussionAssistantCitation(
            origin=c.get("origin"),
            origin_id=c.get("origin_id"),
            label=c.get("label", ""),
            resource_type=c.get("resource_type"),
        )
        for c in result_dict.get("citations", [])
    ]


def _build_actions(result_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build suggested actions from an AI result dict."""
    return [
        {
            "action_type": a.get("type", a.get("action_type", "")),
            "summary": a.get("summary", ""),
            "payload": a.get("payload", {}),
        }
        for a in result_dict.get("actions", [])
    ]


def _build_ai_response(result_dict: Dict[str, Any], model: str) -> DiscussionAssistantResponse:
    """Build a DiscussionAssistantResponse from an orchestrator result dict."""
    return DiscussionAssistantResponse(
        message=result_dict.get("message", ""),
        citations=_build_citations(result_dict),
        reasoning_used=result_dict.get("reasoning_used", False),
        model=result_dict.get("model_used", model),
        usage=result_dict.get("usage"),
        suggested_actions=_build_actions(result_dict),
    )


def _generate_unique_slug(db: Session, project_id: UUID, base: str) -> str:
    slug = base
    counter = 2
    while (
        db.query(ProjectDiscussionChannel)
        .filter(
            ProjectDiscussionChannel.project_id == project_id,
            ProjectDiscussionChannel.slug == slug,
        )
        .first()
    ):
        slug = f"{base}-{counter}"
        counter += 1
    return slug


def _ensure_default_channel(db: Session, project) -> ProjectDiscussionChannel:
    channel = (
        db.query(ProjectDiscussionChannel)
        .filter(
            ProjectDiscussionChannel.project_id == project.id,
            ProjectDiscussionChannel.is_default.is_(True),
        )
        .first()
    )
    if channel:
        return channel

    slug = _generate_unique_slug(db, project.id, "general")
    channel = ProjectDiscussionChannel(
        project_id=project.id,
        name="General",
        slug=slug,
        is_default=True,
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return channel


def _get_channel_or_404(db: Session, project, channel_id: UUID) -> ProjectDiscussionChannel:
    channel = (
        db.query(ProjectDiscussionChannel)
        .filter(
            ProjectDiscussionChannel.project_id == project.id,
            ProjectDiscussionChannel.id == channel_id,
        )
        .first()
    )
    if not channel:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Channel not found")
    return channel


def _serialize_attachment(attachment: ProjectDiscussionMessageAttachment) -> DiscussionMessageAttachmentResponse:
    attachment_type = (
        attachment.attachment_type.value
        if hasattr(attachment.attachment_type, "value")
        else attachment.attachment_type
    )
    return DiscussionMessageAttachmentResponse(
        id=attachment.id,
        message_id=attachment.message_id,
        attachment_type=attachment_type,
        title=attachment.title,
        url=attachment.url,
        document_id=attachment.document_id,
        paper_id=attachment.paper_id,
        reference_id=attachment.reference_id,
        meeting_id=attachment.meeting_id,
        details=attachment.details or {},
        created_at=attachment.created_at,
        created_by=attachment.created_by,
    )


def _serialize_message(message: ProjectDiscussionMessage, reply_count: int = 0) -> DiscussionMessageResponse:
    attachments = [
        _serialize_attachment(attachment)
        for attachment in getattr(message, "attachments", [])
    ]

    user_obj = message.user
    display_name = (
        getattr(user_obj, "name", None)
        or getattr(user_obj, "display_name", None)
        or " ".join(filter(None, [getattr(user_obj, "first_name", None), getattr(user_obj, "last_name", None)])).strip()
    )
    if not display_name:
        display_name = user_obj.email.split("@")[0] if user_obj.email else "Unknown user"

    return DiscussionMessageResponse(
        id=message.id,
        project_id=message.project_id,
        channel_id=message.channel_id,
        user_id=message.user_id,
        user=DiscussionMessageUserInfo(
            id=message.user.id,
            name=display_name,
            email=message.user.email,
        ),
        content=message.content if not message.is_deleted else "[This message has been deleted]",
        parent_id=message.parent_id,
        is_edited=message.is_edited,
        is_deleted=message.is_deleted,
        created_at=message.created_at,
        updated_at=message.updated_at,
        reply_count=reply_count,
        attachments=attachments,
    )


def _serialize_channel(
    channel: ProjectDiscussionChannel,
    stats_map: Optional[Dict[UUID, Dict[str, int]]] = None,
) -> DiscussionChannelSummary:
    from app.schemas.project_discussion import ChannelScopeConfig

    stats = stats_map.get(channel.id) if stats_map else None
    stats_model = None
    if stats:
        stats_model = DiscussionStats(
            project_id=channel.project_id,
            total_messages=stats.get("total_messages", 0),
            total_threads=stats.get("total_threads", 0),
            channel_id=channel.id,
        )

    # Parse scope from JSONB - convert dict to ChannelScopeConfig
    scope_value = None
    if channel.scope and isinstance(channel.scope, dict):
        scope_value = ChannelScopeConfig(
            paper_ids=channel.scope.get("paper_ids"),
            reference_ids=channel.scope.get("reference_ids"),
            meeting_ids=channel.scope.get("meeting_ids"),
        )

    return DiscussionChannelSummary(
        id=channel.id,
        project_id=channel.project_id,
        name=channel.name,
        slug=channel.slug,
        description=channel.description,
        is_default=channel.is_default,
        is_archived=channel.is_archived,
        scope=scope_value,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
        stats=stats_model,
    )


def _prepare_resource_details(resource: ProjectDiscussionChannelResource) -> Dict[str, Any]:
    """Derive up-to-date metadata for a channel resource."""

    details: Dict[str, Any] = dict(resource.details or {})

    if resource.resource_type == ProjectDiscussionResourceType.PAPER:
        paper = getattr(resource, "paper", None)
        if paper:
            details.update({"title": paper.title})
            if paper.summary:
                details["summary"] = paper.summary
            elif paper.abstract:
                details["summary"] = paper.abstract
            if paper.status:
                details["status"] = paper.status
            if paper.authors:
                details["authors"] = list(paper.authors)
            if paper.year:
                details["year"] = paper.year
    elif resource.resource_type == ProjectDiscussionResourceType.REFERENCE:
        reference = getattr(resource, "reference", None)
        if reference:
            details.update({"title": reference.title})
            if reference.summary:
                details["summary"] = reference.summary
            elif reference.abstract:
                details["summary"] = reference.abstract
            if reference.authors:
                details["authors"] = list(reference.authors)
            if reference.year:
                details["year"] = reference.year
            if reference.source:
                details["source"] = reference.source
            if reference.doi:
                details["doi"] = reference.doi
            if reference.url:
                details["url"] = reference.url
    elif resource.resource_type == ProjectDiscussionResourceType.MEETING:
        meeting = getattr(resource, "meeting", None)
        if meeting:
            status_value = meeting.status.value if hasattr(meeting.status, "value") else meeting.status
            details.setdefault("status", status_value)
            details.setdefault("has_transcript", bool(meeting.transcript))
            from app.api.v1.project_meetings import _resolved_meeting_summary  # avoid cyclic import at module load
            from app.api.v1.project_meetings import _extract_transcript_text  # helper for transcript content

            summary_value = _resolved_meeting_summary(meeting)
            if summary_value:
                details["title"] = summary_value
            if meeting.created_at:
                details["created_at"] = meeting.created_at.isoformat()
            transcript_text = _extract_transcript_text(meeting.transcript)
            if transcript_text:
                details["summary"] = transcript_text
            else:
                fallback_summary = meeting.summary or getattr(meeting, "agenda", None)
                if fallback_summary and not details.get("summary"):
                    details["summary"] = fallback_summary
            if "title" not in details:
                details["title"] = (
                    f"Meeting on {meeting.created_at.strftime('%Y-%m-%d')}"
                    if meeting.created_at
                    else "Meeting"
                )

    return {key: value for key, value in details.items() if value is not None}


def _serialize_resource(resource: ProjectDiscussionChannelResource) -> DiscussionChannelResourceResponse:
    resource_type = (
        resource.resource_type.value
        if hasattr(resource.resource_type, "value")
        else resource.resource_type
    )
    details = _prepare_resource_details(resource)
    return DiscussionChannelResourceResponse(
        id=resource.id,
        channel_id=resource.channel_id,
        resource_type=resource_type,
        paper_id=resource.paper_id,
        reference_id=resource.reference_id,
        meeting_id=resource.meeting_id,
        details=details,
        added_by=resource.added_by,
        created_at=resource.created_at,
    )


def _serialize_task(task: ProjectDiscussionTask) -> DiscussionTaskResponse:
    status_value = task.status.value if hasattr(task.status, "value") else task.status
    return DiscussionTaskResponse(
        id=task.id,
        project_id=task.project_id,
        channel_id=task.channel_id,
        message_id=task.message_id,
        title=task.title,
        description=task.description,
        status=status_value,
        assignee_id=task.assignee_id,
        due_date=task.due_date,
        details=task.details or {},
        created_by=task.created_by,
        updated_by=task.updated_by,
        completed_at=task.completed_at,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _parse_task_status(value: Optional[str]) -> Optional[ProjectDiscussionTaskStatus]:
    if value is None:
        return None
    try:
        return ProjectDiscussionTaskStatus(value)
    except ValueError as exc:  # pragma: no cover - FastAPI will serialize
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task status") from exc


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


class OpenRouterModelInfo(BaseModel):
    id: str
    name: str
    provider: str
    supports_reasoning: bool = False


class OpenRouterModelListResponse(BaseModel):
    models: List[OpenRouterModelInfo]
    source: str
    warning: Optional[str] = None
    key_source: Optional[str] = None


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
                    elif event.get("type") == "result":
                        final_result = event.get("data", {})
                        response_model = _build_ai_response(final_result, selected_model)
                        yield "data: " + json.dumps({"type": "result", "payload": response_model.model_dump(mode="json")}) + "\n\n"
                    elif event.get("type") == "error":
                        yield "data: " + json.dumps({"type": "error", "message": event.get("message", "Error")}) + "\n\n"

                # Persist completed exchange
                if final_result:
                    response_model = _build_ai_response(final_result, selected_model)
                    payload_dict = response_model.model_dump(mode="json")
                    conversation_state = final_result.get("conversation_state", {})

                    await asyncio.to_thread(
                        _persist_assistant_exchange,
                        proj_id, chan_id, user_id, exchange_id,
                        question_text, payload_dict, exchange_created_at,
                        conversation_state, "completed",
                    )
                    await _broadcast_discussion_event(
                        proj_id, chan_id, "assistant_reply",
                        {"exchange": {
                            "id": exchange_id,
                            "question": question_text,
                            "response": payload_dict,
                            "created_at": exchange_created_at,
                            "author": author_info,
                            "status": "completed",
                        }},
                    )
                    try:
                        await asyncio.to_thread(SubscriptionService.increment_usage, db, user_id, "discussion_ai_calls", credit_cost)
                    except Exception as e:
                        logger.error(f"Failed to increment discussion AI usage for user {user_id}: {e}")

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


# ============================================================================
# Paper Action Endpoint (for AI-suggested paper creation/editing)
# ============================================================================

class PaperActionRequest(BaseModel):
    action_type: str  # "create_paper" or "edit_paper"
    payload: Dict[str, Any]


class PaperActionResponse(BaseModel):
    success: bool
    paper_id: Optional[str] = None
    reference_id: Optional[str] = None
    message: str
    ingestion_status: Optional[str] = None  # 'success', 'failed', 'no_pdf', 'pending'


@router.post("/projects/{project_id}/discussion/paper-action")
def execute_paper_action(
    project_id: str,
    request: PaperActionRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PaperActionResponse:
    """Execute a paper action suggested by the discussion AI."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    if request.action_type == "create_paper":
        return _handle_create_paper(db, project, current_user, request.payload)
    elif request.action_type == "edit_paper":
        return _handle_edit_paper(db, project, current_user, request.payload)
    elif request.action_type == "add_reference":
        return _handle_add_reference(db, project, current_user, request.payload, background_tasks)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown action type: {request.action_type}"
        )


def _handle_create_paper(
    db: Session,
    project,
    user: User,
    payload: Dict[str, Any],
) -> PaperActionResponse:
    """Create a new paper from AI suggestion."""
    from app.constants.paper_templates import PAPER_TEMPLATES

    title = str(payload.get("title", "Untitled Paper")).strip()
    paper_type = str(payload.get("paper_type", "research")).strip()
    authoring_mode = str(payload.get("authoring_mode", "rich")).strip()  # Default to rich for AI content
    abstract = payload.get("abstract")
    objectives = payload.get("objectives", [])
    keywords = payload.get("keywords", [])
    initial_content = payload.get("content")  # AI-generated content

    # Ensure objectives is a list
    if not isinstance(objectives, list):
        objectives = []
    objectives = [str(obj).strip() for obj in objectives if obj]

    # Ensure keywords is a list
    if not isinstance(keywords, list):
        keywords = []
    keywords = [str(kw).strip() for kw in keywords if kw]

    # Validate paper_type
    valid_types = {"research", "review", "case_study"}
    if paper_type not in valid_types:
        paper_type = "research"

    # Validate authoring_mode
    if authoring_mode not in {"latex", "rich"}:
        authoring_mode = "rich"

    content = None
    content_json: Dict[str, Any] = {}

    # If AI provided initial content, use it directly
    if initial_content:
        if authoring_mode == "latex":
            content_json = {
                "authoring_mode": "latex",
                "latex_source": initial_content
            }
        else:
            content = initial_content
            content_json = {"authoring_mode": "rich"}
    else:
        # Fall back to template
        template = next(
            (t for t in PAPER_TEMPLATES if t["id"] == paper_type),
            PAPER_TEMPLATES[0] if PAPER_TEMPLATES else None
        )

        if template:
            if authoring_mode == "latex":
                content_json = {
                    "authoring_mode": "latex",
                    "latex_source": template.get("latexTemplate", "")
                }
            else:
                content = template.get("richTemplate", "")
                content_json = {"authoring_mode": "rich"}
        else:
            # Fallback if no template found
            if authoring_mode == "latex":
                content_json = {
                    "authoring_mode": "latex",
                    "latex_source": "\\documentclass{article}\n\\begin{document}\n\n\\end{document}"
                }
            else:
                content = "# " + title + "\n\n"
                content_json = {"authoring_mode": "rich"}

    # Use centralized paper service for creation + member + initial snapshot
    from app.services.paper_service import create_paper

    paper = create_paper(
        db=db,
        title=title,
        owner_id=user.id,
        project_id=project.id,
        content=content,
        content_json=content_json,
        abstract=abstract if abstract else None,
        paper_type=paper_type,
        status="draft",
        objectives=objectives if objectives else None,
        keywords=keywords if keywords else None,
        snapshot_label="AI-generated initial version",
    )

    logger.info(
        "Paper created via discussion AI: paper_id=%s title=%s type=%s mode=%s",
        paper.id, title, paper_type, authoring_mode
    )

    return PaperActionResponse(
        success=True,
        paper_id=str(paper.id),
        message=f"Created '{title}' ({paper_type}, {authoring_mode})"
    )


def _handle_edit_paper(
    db: Session,
    project,
    user: User,
    payload: Dict[str, Any],
) -> PaperActionResponse:
    """Apply an edit to an existing paper from AI suggestion."""
    paper_id = payload.get("paper_id")
    original = str(payload.get("original", "")).strip()
    proposed = str(payload.get("proposed", "")).strip()

    if not paper_id:
        return PaperActionResponse(success=False, message="Missing paper_id")
    if not original:
        return PaperActionResponse(success=False, message="Missing original text")
    if not proposed:
        return PaperActionResponse(success=False, message="Missing proposed text")
    if original == proposed:
        return PaperActionResponse(success=False, message="Original and proposed text are identical")

    # Find paper
    try:
        paper_uuid = UUID(str(paper_id))
    except ValueError:
        return PaperActionResponse(success=False, message="Invalid paper_id format")

    paper = db.query(ResearchPaper).filter(
        ResearchPaper.id == paper_uuid,
        ResearchPaper.project_id == project.id
    ).first()

    if not paper:
        return PaperActionResponse(success=False, message="Paper not found in project")

    # Check user has edit permission
    member = db.query(PaperMember).filter(
        PaperMember.paper_id == paper_uuid,
        PaperMember.user_id == user.id
    ).first()
    if not member and paper.owner_id != user.id:
        return PaperActionResponse(success=False, message="No permission to edit this paper")

    # Apply edit based on authoring mode
    if isinstance(paper.content_json, dict) and paper.content_json.get("authoring_mode") == "latex":
        latex_source = paper.content_json.get("latex_source", "")
        if original not in latex_source:
            return PaperActionResponse(
                success=False,
                message="Original text not found in paper. The content may have changed."
            )

        new_latex = latex_source.replace(original, proposed, 1)
        paper.content_json = {
            **paper.content_json,
            "latex_source": new_latex
        }
    else:
        if not paper.content or original not in paper.content:
            return PaperActionResponse(
                success=False,
                message="Original text not found in paper. The content may have changed."
            )

        paper.content = paper.content.replace(original, proposed, 1)

    db.commit()

    logger.info(
        "Paper edited via discussion AI: paper_id=%s original_len=%d proposed_len=%d",
        paper_id, len(original), len(proposed)
    )

    return PaperActionResponse(
        success=True,
        paper_id=str(paper.id),
        message="Edit applied successfully"
    )


def _handle_add_reference(
    db: Session,
    project,
    user: User,
    payload: Dict[str, Any],
    background_tasks: Optional[BackgroundTasks] = None,
) -> PaperActionResponse:
    """Add a discovered paper as a project reference."""
    title = payload.get("title")
    authors = payload.get("authors", [])
    year = payload.get("year")
    doi = payload.get("doi")
    url = payload.get("url")
    abstract = payload.get("abstract")
    source = payload.get("source")
    pdf_url = payload.get("pdf_url")
    is_open_access = payload.get("is_open_access", False)

    if not title:
        return PaperActionResponse(success=False, message="Title is required")

    # Normalize authors to list (Reference model expects ARRAY)
    authors_list = []
    if isinstance(authors, list):
        authors_list = [str(a) for a in authors if a]
    elif isinstance(authors, str) and authors:
        authors_list = [a.strip() for a in authors.split(",") if a.strip()]

    # Check for existing reference by DOI for this user
    existing_ref = None
    if doi:
        existing_ref = db.query(Reference).filter(
            Reference.doi == doi,
            Reference.owner_id == user.id
        ).first()

    if existing_ref:
        ref = existing_ref
        # Update pdf_url if not set and we have one now
        if pdf_url and not ref.pdf_url:
            ref.pdf_url = pdf_url
            ref.is_open_access = is_open_access
    else:
        # Create new reference with owner_id (required field)
        ref = Reference(
            title=title,
            authors=authors_list,
            year=year,
            doi=doi,
            url=url,
            abstract=abstract,
            source=source or "discussion_ai",
            owner_id=user.id,
            pdf_url=pdf_url,
            is_open_access=is_open_access
        )
        db.add(ref)
        db.flush()

    # Check if already linked to project
    existing_link = db.query(ProjectReference).filter(
        ProjectReference.project_id == project.id,
        ProjectReference.reference_id == ref.id
    ).first()

    if existing_link:
        return PaperActionResponse(
            success=True,  # Still success - reference exists
            reference_id=str(ref.id),
            message="Reference already exists in project"
        )

    # Link to project
    from app.models.project_reference import ProjectReferenceStatus, ProjectReferenceOrigin
    project_ref = ProjectReference(
        project_id=project.id,
        reference_id=ref.id,
        status=ProjectReferenceStatus.APPROVED,
        origin=ProjectReferenceOrigin.MANUAL_ADD
    )
    db.add(project_ref)
    db.commit()

    # Truncate title for message
    short_title = title[:50] + "..." if len(title) > 50 else title
    message = f"Added '{short_title}' to references"
    ingestion_status = None

    # Run PDF ingestion synchronously to return actual status
    if pdf_url:
        try:
            from app.services.reference_ingestion_service import ingest_reference_pdf
            success = ingest_reference_pdf(db, ref, owner_id=str(user.id))
            if success:
                ingestion_status = "success"
                message += " (PDF ingested for full-text analysis)"
            else:
                ingestion_status = "failed"
                message += " (PDF ingestion failed - you can upload manually)"
            logger.info("PDF ingestion for reference %s: %s", ref.id, ingestion_status)
        except Exception as e:
            logger.warning("PDF ingestion failed for reference %s: %s", ref.id, e)
            ingestion_status = "failed"
            message += " (PDF ingestion failed - you can upload manually)"
    else:
        ingestion_status = "no_pdf"
        message += " (no PDF available - abstract only)"

    logger.info(
        "Reference added via discussion AI: ref_id=%s title=%s project_id=%s ingestion=%s",
        ref.id, title[:50], project.id, ingestion_status
    )

    return PaperActionResponse(
        success=True,
        paper_id=str(ref.id),
        reference_id=str(ref.id),
        message=message,
        ingestion_status=ingestion_status
    )


# ============================================================================
# Search References Endpoint (for AI-assisted reference discovery)
# ============================================================================

class SearchReferencesRequest(BaseModel):
    query: str
    sources: Optional[List[str]] = None
    max_results: int = 10
    open_access_only: bool = False  # If true, only return papers with PDF available


class DiscoveredPaperResponse(BaseModel):
    id: str
    title: str
    authors: List[str]
    year: Optional[int] = None
    abstract: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: str
    relevance_score: Optional[float] = None
    pdf_url: Optional[str] = None
    is_open_access: bool = False
    journal: Optional[str] = None


class SearchReferencesResponse(BaseModel):
    papers: List[DiscoveredPaperResponse]
    total_found: int
    query: str


@router.post("/projects/{project_id}/discussion/search-references")
async def search_references(
    project_id: str,
    request: SearchReferencesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SearchReferencesResponse:
    """Search for academic papers using the paper discovery service."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    from app.services.paper_discovery_service import PaperDiscoveryService

    # Default sources for discussion AI search (fast, reliable sources)
    sources = request.sources or ["arxiv", "semantic_scholar", "openalex", "crossref", "pubmed", "europe_pmc"]
    max_results = min(request.max_results, 20)  # Cap at 20 results

    # Create discovery service and search
    discovery_service = PaperDiscoveryService()

    try:
        # Request more results if filtering for open access, to ensure we get enough
        search_max = max_results * 3 if request.open_access_only else max_results

        result = await discovery_service.discover_papers(
            query=request.query,
            max_results=search_max,
            sources=sources,
            fast_mode=True,  # Use fast mode for chat responsiveness
        )

        # Filter for open access if requested
        source_papers = result.papers
        if request.open_access_only:
            source_papers = [p for p in source_papers if p.pdf_url or p.open_access_url]

        # Convert to response format
        papers = []
        for idx, p in enumerate(source_papers[:max_results]):
            # Create unique ID for frontend tracking using DOI or index
            unique_key = p.get_unique_key() if hasattr(p, 'get_unique_key') else str(idx)
            paper_id = f"{p.source}:{unique_key}"

            # Parse authors
            authors_list = []
            if p.authors:
                if isinstance(p.authors, list):
                    authors_list = [str(a) for a in p.authors]
                elif isinstance(p.authors, str):
                    authors_list = [a.strip() for a in p.authors.split(",")]

            papers.append(DiscoveredPaperResponse(
                id=paper_id,
                title=p.title,
                authors=authors_list,
                year=p.year,
                abstract=p.abstract[:500] if p.abstract else None,
                doi=p.doi,
                url=p.url,
                source=p.source,
                relevance_score=p.relevance_score,
                pdf_url=p.pdf_url or p.open_access_url,
                is_open_access=p.is_open_access,
                journal=p.journal,
            ))

        # Ensure we never return more than requested (defensive limit)
        final_papers = papers[:max_results]

        return SearchReferencesResponse(
            papers=final_papers,
            total_found=len(result.papers),
            query=request.query
        )
    finally:
        await discovery_service.close()


# ============================================================================
# Batch Search References Endpoint (for multi-topic search)
# ============================================================================

class TopicQuery(BaseModel):
    """A single topic query for batch search."""
    topic: str  # Display name for grouping (e.g., "Mixture of Experts")
    query: str  # Actual search query (e.g., "mixture of experts 2025")
    max_results: int = 5


class BatchSearchRequest(BaseModel):
    """Request for batch search across multiple topics."""
    queries: List[TopicQuery]
    open_access_only: bool = False


class TopicResult(BaseModel):
    """Results for a single topic in batch search."""
    topic: str
    query: str
    papers: List[DiscoveredPaperResponse]
    count: int


class BatchSearchResponse(BaseModel):
    """Response for batch search across multiple topics."""
    results: List[TopicResult]
    total_found: int


@router.post("/projects/{project_id}/discussion/batch-search-references")
async def batch_search_references(
    project_id: str,
    request: BatchSearchRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchSearchResponse:
    """
    Search for academic papers across multiple topics in one call.
    Returns results grouped by topic for easy consumption.
    """
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    from app.services.paper_discovery_service import PaperDiscoveryService

    # Limit to 5 topics max per request
    queries = request.queries[:5]
    sources = ["arxiv", "semantic_scholar", "openalex", "crossref", "pubmed", "europe_pmc"]

    results: List[TopicResult] = []
    total_found = 0

    # Track seen papers across topics for deduplication
    seen_keys: set = set()

    discovery_service = PaperDiscoveryService()

    try:
        for topic_query in queries:
            max_results = min(topic_query.max_results, 10)  # Cap per topic
            search_max = max_results * 2 if request.open_access_only else max_results

            result = await discovery_service.discover_papers(
                query=topic_query.query,
                max_results=search_max,
                sources=sources,
                fast_mode=True,
            )

            # Filter for open access if requested
            source_papers = result.papers
            if request.open_access_only:
                source_papers = [p for p in source_papers if p.pdf_url or p.open_access_url]

            # Convert to response format with cross-topic deduplication
            papers = []
            for idx, p in enumerate(source_papers[:max_results]):
                unique_key = p.get_unique_key() if hasattr(p, 'get_unique_key') else f"{topic_query.topic}:{idx}"

                # Skip if already seen in another topic
                if unique_key in seen_keys:
                    continue
                seen_keys.add(unique_key)

                paper_id = f"{p.source}:{unique_key}"

                # Parse authors
                authors_list = []
                if p.authors:
                    if isinstance(p.authors, list):
                        authors_list = [str(a) for a in p.authors]
                    elif isinstance(p.authors, str):
                        authors_list = [a.strip() for a in p.authors.split(",")]

                papers.append(DiscoveredPaperResponse(
                    id=paper_id,
                    title=p.title,
                    authors=authors_list,
                    year=p.year,
                    abstract=p.abstract[:500] if p.abstract else None,
                    doi=p.doi,
                    url=p.url,
                    source=p.source,
                    relevance_score=p.relevance_score,
                    pdf_url=p.pdf_url or p.open_access_url,
                    is_open_access=p.is_open_access,
                    journal=p.journal,
                ))

            results.append(TopicResult(
                topic=topic_query.topic,
                query=topic_query.query,
                papers=papers,
                count=len(papers)
            ))
            total_found += len(papers)

        return BatchSearchResponse(
            results=results,
            total_found=total_found
        )
    finally:
        await discovery_service.close()


def _discussion_session_id(project_id: UUID, channel_id: UUID) -> str:
    return f"discussion:{project_id}:{channel_id}"


def _display_name_for_user(user: User) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last}".strip()
    if first:
        return first
    if user.email:
        return user.email.split("@")[0]
    return "Unknown"


def _build_assistant_author_payload(user: Optional[User]) -> Optional[Dict[str, Any]]:
    if not user:
        return None

    display = _display_name_for_user(user)
    return {
        "id": str(user.id),
        "name": {
            "display": display,
            "first": (user.first_name or "").strip(),
            "last": (user.last_name or "").strip(),
        },
    }


async def _broadcast_discussion_event(
    project_id: str,
    channel_id: UUID,
    event: str,
    payload: Dict[str, Any],
):
    message = {
        "type": "discussion_event",
        "event": event,
        "project_id": str(project_id),
        "channel_id": str(channel_id),
        **payload,
    }
    session_key = _discussion_session_id(project_id, channel_id)
    await connection_manager.broadcast_to_session(session_key, message)


def _persist_assistant_exchange(
    project_id: str,
    channel_id: UUID,
    author_id: Optional[UUID],
    exchange_id: str,
    question: str,
    response_payload: Dict[str, Any],
    created_at_iso: Optional[str] = None,
    conversation_state: Optional[Dict[str, Any]] = None,
    status: str = "completed",
    status_message: Optional[str] = None,
):
    """
    Persist an assistant exchange to the database.

    Args:
        conversation_state: State machine state to persist for next turn.
            This tracks whether clarification has been asked, enabling
            the "one clarification max" rule.
        status: Exchange status (processing, completed, failed)
        status_message: Optional status message for processing state
    """
    db = SessionLocal()
    try:
        try:
            exchange_uuid = UUID(exchange_id)
        except Exception:
            exchange_uuid = uuid4()

        exchange = db.query(ProjectDiscussionAssistantExchange).filter_by(id=exchange_uuid).one_or_none()

        timestamp = None
        if created_at_iso:
            try:
                timestamp = datetime.fromisoformat(created_at_iso.replace('Z', '+00:00'))
            except Exception:
                timestamp = None

        if exchange:
            exchange.question = question
            exchange.response = response_payload
            exchange.project_id = project_id
            exchange.channel_id = channel_id
            exchange.author_id = author_id
            exchange.status = status
            exchange.status_message = status_message
            if conversation_state is not None:
                exchange.conversation_state = conversation_state
            if timestamp:
                exchange.created_at = timestamp
        else:
            exchange = ProjectDiscussionAssistantExchange(
                id=exchange_uuid,
                project_id=project_id,
                channel_id=channel_id,
                author_id=author_id,
                question=question,
                response=response_payload,
                conversation_state=conversation_state or {},
                created_at=timestamp,
                status=status,
                status_message=status_message,
            )
            db.add(exchange)

        db.commit()
    except Exception:  # pragma: no cover - background logging
        db.rollback()
        logger.exception(
            "Failed to persist discussion assistant exchange",
            extra={
                "project_id": str(project_id),
                "channel_id": str(channel_id),
                "exchange_id": exchange_id,
            },
        )
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────────────────────
# Channel Artifacts
# ─────────────────────────────────────────────────────────────────────────────


class DiscussionArtifactResponse(BaseModel):
    id: str
    title: str
    filename: str
    format: str
    artifact_type: str
    mime_type: str
    file_size: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None


class DiscussionArtifactDownloadResponse(BaseModel):
    id: str
    title: str
    filename: str
    content_base64: str
    mime_type: str


@router.get(
    "/projects/{project_id}/discussion/channels/{channel_id}/artifacts",
    response_model=List[DiscussionArtifactResponse],
)
async def list_channel_artifacts(
    project_id: str,
    channel_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all artifacts for a channel."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    # Verify channel belongs to project
    channel = db.query(ProjectDiscussionChannel).filter(
        ProjectDiscussionChannel.id == channel_id,
        ProjectDiscussionChannel.project_id == project_id,
    ).first()
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found")

    artifacts = db.query(DiscussionArtifact).filter(
        DiscussionArtifact.channel_id == channel_id
    ).order_by(DiscussionArtifact.created_at.desc()).all()

    return [
        DiscussionArtifactResponse(
            id=str(a.id),
            title=a.title,
            filename=a.filename,
            format=a.format.value if hasattr(a.format, 'value') else str(a.format),
            artifact_type=a.artifact_type,
            mime_type=a.mime_type,
            file_size=a.file_size,
            created_at=a.created_at,
            created_by=str(a.created_by) if a.created_by else None,
        )
        for a in artifacts
    ]


@router.get(
    "/projects/{project_id}/discussion/channels/{channel_id}/artifacts/{artifact_id}",
    response_model=DiscussionArtifactDownloadResponse,
)
async def get_artifact(
    project_id: str,
    channel_id: UUID,
    artifact_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get artifact content for download."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

    artifact = db.query(DiscussionArtifact).filter(
        DiscussionArtifact.id == artifact_id,
        DiscussionArtifact.channel_id == channel_id,
    ).first()

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return DiscussionArtifactDownloadResponse(
        id=str(artifact.id),
        title=artifact.title,
        filename=artifact.filename,
        content_base64=artifact.content_base64,
        mime_type=artifact.mime_type,
    )


@router.delete(
    "/projects/{project_id}/discussion/channels/{channel_id}/artifacts/{artifact_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_artifact(
    project_id: str,
    channel_id: UUID,
    artifact_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an artifact."""
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    artifact = db.query(DiscussionArtifact).filter(
        DiscussionArtifact.id == artifact_id,
        DiscussionArtifact.channel_id == channel_id,
    ).first()

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    db.delete(artifact)
    db.commit()

    return Response(status_code=status.HTTP_204_NO_CONTENT)
