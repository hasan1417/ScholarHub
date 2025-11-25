from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

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

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.core.security import verify_token
from app.database import SessionLocal, get_db
from app.models import (
    Meeting,
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
)
from app.schemas.project_discussion import (
    DiscussionAssistantCitation,
    DiscussionAssistantRequest,
    DiscussionAssistantResponse,
    DiscussionAssistantExchangeResponse,
    DiscussionAssistantSuggestedAction,
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
from app.services.discussion_ai import DiscussionAIService
from app.services.discussion_ai.types import AssistantReply
from app.services.websocket_manager import connection_manager

router = APIRouter()

logger = logging.getLogger(__name__)

_discussion_ai_core = AIService()

_slug_regex = re.compile(r"[^a-z0-9]+")


def _slugify(value: str) -> str:
    base = _slug_regex.sub("-", value.lower()).strip("-")
    return base or "channel"


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
    stats = stats_map.get(channel.id) if stats_map else None
    stats_model = None
    if stats:
        stats_model = DiscussionStats(
            project_id=channel.project_id,
            total_messages=stats.get("total_messages", 0),
            total_threads=stats.get("total_threads", 0),
            channel_id=channel.id,
        )

    return DiscussionChannelSummary(
        id=channel.id,
        project_id=channel.project_id,
        name=channel.name,
        slug=channel.slug,
        description=channel.description,
        is_default=channel.is_default,
        is_archived=channel.is_archived,
        created_at=channel.created_at,
        updated_at=channel.updated_at,
        stats=stats_model,
    )


def _build_assistant_response_model(reply: AssistantReply) -> DiscussionAssistantResponse:
    citations = [
        DiscussionAssistantCitation(
            origin=citation.origin,
            origin_id=citation.origin_id,
            label=citation.label,
            resource_type=citation.resource_type,
        )
        for citation in reply.citations
    ]

    suggested_actions = [
        {
            "action_type": action.action_type,
            "summary": action.summary,
            "payload": action.payload,
        }
        for action in reply.suggested_actions
    ]

    return DiscussionAssistantResponse(
        message=reply.message,
        citations=citations,
        reasoning_used=reply.reasoning_used,
        model=reply.model,
        usage=reply.usage,
        suggested_actions=suggested_actions,
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
    project_id: UUID,
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
    project_id: UUID,
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
    project_id: UUID,
    message_data: DiscussionMessageCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionMessageResponse:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

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
    project_id: UUID,
    message_id: UUID,
    message_data: DiscussionMessageUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionMessageResponse:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

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
    project_id: UUID,
    message_id: UUID,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    project = get_project_or_404(db, project_id)
    membership = ensure_project_member(db, project, current_user)

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
    is_admin = membership.role == ProjectRole.ADMIN

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
    project_id: UUID,
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
    project_id: UUID,
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
    project_id: UUID,
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
    project_id: UUID,
    payload: DiscussionChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionChannelSummary:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])

    base_slug = _slugify(payload.slug or payload.name)
    slug = _generate_unique_slug(db, project.id, base_slug)

    channel = ProjectDiscussionChannel(
        project_id=project.id,
        name=payload.name.strip(),
        slug=slug,
        description=payload.description,
        created_by=current_user.id,
        updated_by=current_user.id,
    )

    db.add(channel)
    db.commit()
    db.refresh(channel)

    return _serialize_channel(channel)


@router.put("/projects/{project_id}/discussion/channels/{channel_id}")
def update_discussion_channel(
    project_id: UUID,
    channel_id: UUID,
    payload: DiscussionChannelUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionChannelSummary:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user, roles=[ProjectRole.ADMIN, ProjectRole.EDITOR])
    channel = _get_channel_or_404(db, project, channel_id)

    if payload.name:
        channel.name = payload.name.strip()
    if payload.description is not None:
        channel.description = payload.description
    if payload.is_archived is not None and not channel.is_default:
        channel.is_archived = payload.is_archived

    channel.updated_by = current_user.id

    db.commit()
    db.refresh(channel)

    return _serialize_channel(channel)


@router.get("/projects/{project_id}/discussion/channels/{channel_id}/resources")
def list_channel_resources(
    project_id: UUID,
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
    project_id: UUID,
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
    project_id: UUID,
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


@router.post(
    "/projects/{project_id}/discussion/channels/{channel_id}/assistant",
    response_model=DiscussionAssistantResponse,
)
def invoke_discussion_assistant(
    project_id: UUID,
    channel_id: UUID,
    payload: DiscussionAssistantRequest,
    background_tasks: BackgroundTasks,
    stream: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
    channel = _get_channel_or_404(db, project, channel_id)

    assistant = DiscussionAIService(db=db, ai_service=_discussion_ai_core)
    display_name = _display_name_for_user(current_user)
    author_info = {
        "id": str(current_user.id),
        "name": {
            "first": current_user.first_name or "",
            "last": current_user.last_name or "",
            "display": display_name,
        },
    }
    logger.info(f"🔍 AI Assistant - User: {current_user.email}, first_name: '{current_user.first_name}', last_name: '{current_user.last_name}', display_name: '{display_name}', author_info: {author_info}")

    if stream:
        def event_iterator():
            try:
                for event in assistant.stream_reply(
                    project,
                    channel,
                    payload.question,
                    reasoning=payload.reasoning,
                    scope=payload.scope,
                ):
                    if event.get("type") == "token":
                        yield "data: " + json.dumps({"type": "token", "content": event.get("content", "")}) + "\n\n"
                    elif event.get("type") == "result":
                        reply_obj = event.get("reply")
                        if isinstance(reply_obj, AssistantReply):
                            response_model = _build_assistant_response_model(reply_obj)
                            payload_dict = response_model.model_dump(mode="json")
                            exchange_payload = {
                                "id": str(uuid4()),
                                "question": payload.question,
                                "response": payload_dict,
                                "created_at": datetime.utcnow().isoformat() + "Z",
                                "author": author_info,
                            }
                            background_tasks.add_task(
                                _persist_assistant_exchange,
                                project.id,
                                channel.id,
                                current_user.id,
                                exchange_payload["id"],
                                payload.question,
                                payload_dict,
                                exchange_payload["created_at"],
                            )
                            background_tasks.add_task(
                                _broadcast_discussion_event,
                                project.id,
                                channel.id,
                                "assistant_reply",
                                {"exchange": exchange_payload},
                            )
                            yield "data: " + json.dumps({"type": "result", "payload": payload_dict}) + "\n\n"
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.exception("Discussion assistant stream failed", exc_info=exc)
                yield "data: " + json.dumps({"type": "error", "message": "Assistant stream failed"}) + "\n\n"

        return StreamingResponse(event_iterator(), media_type="text/event-stream")

    reply = assistant.generate_reply(
        project,
        channel,
        payload.question,
        reasoning=payload.reasoning,
        scope=payload.scope,
    )

    response_model = _build_assistant_response_model(reply)
    exchange_payload = {
        "id": str(uuid4()),
        "question": payload.question,
        "response": response_model.model_dump(mode="json"),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "author": author_info,
    }
    background_tasks.add_task(
        _persist_assistant_exchange,
        project.id,
        channel.id,
        current_user.id,
        exchange_payload["id"],
        payload.question,
        exchange_payload["response"],
        exchange_payload["created_at"],
    )
    background_tasks.add_task(
        _broadcast_discussion_event,
        project.id,
        channel.id,
        "assistant_reply",
        {"exchange": exchange_payload},
    )

    return response_model


@router.get(
    "/projects/{project_id}/discussion/channels/{channel_id}/assistant-history",
    response_model=List[DiscussionAssistantExchangeResponse],
)
def list_discussion_assistant_history(
    project_id: UUID,
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

    results: List[DiscussionAssistantExchangeResponse] = []
    for exchange in exchanges:
        try:
            response_payload = DiscussionAssistantResponse(**exchange.response)
        except Exception:
            # Fallback to basic structure if stored payload is malformed
            response_payload = DiscussionAssistantResponse(
                message=exchange.response.get("message", ""),
                citations=[
                    DiscussionAssistantCitation(
                        origin=item.get("origin"),
                        origin_id=item.get("origin_id"),
                        label=item.get("label", ""),
                        resource_type=item.get("resource_type"),
                    )
                    for item in exchange.response.get("citations", [])
                ],
                reasoning_used=bool(exchange.response.get("reasoning_used")),
                model=str(exchange.response.get("model", "")),
                usage=exchange.response.get("usage"),
                suggested_actions=[
                    DiscussionAssistantSuggestedAction(
                        action_type=item.get("action_type", ""),
                        summary=item.get("summary", ""),
                        payload=item.get("payload", {}),
                    )
                    for item in exchange.response.get("suggested_actions", [])
                ],
            )

        author_payload = _build_assistant_author_payload(exchange.author)

        results.append(
            DiscussionAssistantExchangeResponse(
                id=exchange.id,
                question=exchange.question,
                response=response_payload,
                created_at=exchange.created_at or datetime.utcnow(),
                author=author_payload,
            )
        )

    return results


@router.get("/projects/{project_id}/discussion/tasks")
def list_discussion_tasks(
    project_id: UUID,
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
    project_id: UUID,
    channel_id: UUID,
    payload: DiscussionTaskCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionTaskResponse:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)
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
    project_id: UUID,
    task_id: UUID,
    payload: DiscussionTaskUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DiscussionTaskResponse:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

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
    project_id: UUID,
    task_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    project = get_project_or_404(db, project_id)
    ensure_project_member(db, project, current_user)

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
    project_id: UUID,
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
    project_id: UUID,
    channel_id: UUID,
    author_id: Optional[UUID],
    exchange_id: str,
    question: str,
    response_payload: Dict[str, Any],
    created_at_iso: Optional[str] = None,
):
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
                created_at=timestamp,
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
