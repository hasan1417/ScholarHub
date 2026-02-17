from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.database import SessionLocal
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
    User,
)
from app.schemas.project_discussion import (
    DiscussionAssistantCitation,
    DiscussionAssistantResponse,
    DiscussionChannelResourceResponse,
    DiscussionChannelSummary,
    DiscussionMessageAttachmentResponse,
    DiscussionMessageResponse,
    DiscussionMessageUserInfo,
    DiscussionStats,
    DiscussionTaskResponse,
)
from app.services.websocket_manager import connection_manager

logger = logging.getLogger(__name__)

_slug_regex = re.compile(r"[^a-z0-9]+")


def slugify(value: str) -> str:
    base = _slug_regex.sub("-", value.lower()).strip("-")
    return base or "channel"


def build_citations(result_dict: Dict[str, Any]) -> List[DiscussionAssistantCitation]:
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


def build_actions(result_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build suggested actions from an AI result dict."""
    return [
        {
            "action_type": a.get("type", a.get("action_type", "")),
            "summary": a.get("summary", ""),
            "payload": a.get("payload", {}),
        }
        for a in result_dict.get("actions", [])
    ]


def build_ai_response(result_dict: Dict[str, Any], model: str) -> DiscussionAssistantResponse:
    """Build a DiscussionAssistantResponse from an orchestrator result dict."""
    return DiscussionAssistantResponse(
        message=result_dict.get("message", ""),
        citations=build_citations(result_dict),
        reasoning_used=result_dict.get("reasoning_used", False),
        model=result_dict.get("model_used", model),
        usage=result_dict.get("usage"),
        suggested_actions=build_actions(result_dict),
    )


def generate_unique_slug(db: Session, project_id: UUID, base: str) -> str:
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


def ensure_default_channel(db: Session, project) -> ProjectDiscussionChannel:
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

    slug = generate_unique_slug(db, project.id, "general")
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


def get_channel_or_404(db: Session, project, channel_id: UUID) -> ProjectDiscussionChannel:
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


def serialize_attachment(attachment: ProjectDiscussionMessageAttachment) -> DiscussionMessageAttachmentResponse:
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


def serialize_message(message: ProjectDiscussionMessage, reply_count: int = 0) -> DiscussionMessageResponse:
    attachments = [
        serialize_attachment(attachment)
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


def serialize_channel(
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


def prepare_resource_details(resource: ProjectDiscussionChannelResource) -> Dict[str, Any]:
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


def serialize_resource(resource: ProjectDiscussionChannelResource) -> DiscussionChannelResourceResponse:
    resource_type = (
        resource.resource_type.value
        if hasattr(resource.resource_type, "value")
        else resource.resource_type
    )
    details = prepare_resource_details(resource)
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


def serialize_task(task: ProjectDiscussionTask) -> DiscussionTaskResponse:
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


def parse_task_status(value: Optional[str]) -> Optional[ProjectDiscussionTaskStatus]:
    if value is None:
        return None
    try:
        return ProjectDiscussionTaskStatus(value)
    except ValueError as exc:  # pragma: no cover - FastAPI will serialize
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid task status") from exc


def discussion_session_id(project_id: UUID, channel_id: UUID) -> str:
    return f"discussion:{project_id}:{channel_id}"


def display_name_for_user(user: User) -> str:
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    if first and last:
        return f"{first} {last}".strip()
    if first:
        return first
    if user.email:
        return user.email.split("@")[0]
    return "Unknown"


def build_assistant_author_payload(user: Optional[User]) -> Optional[Dict[str, Any]]:
    if not user:
        return None

    display = display_name_for_user(user)
    return {
        "id": str(user.id),
        "name": {
            "display": display,
            "first": (user.first_name or "").strip(),
            "last": (user.last_name or "").strip(),
        },
    }


async def broadcast_discussion_event(
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
    session_key = discussion_session_id(project_id, channel_id)
    await connection_manager.broadcast_to_session(session_key, message)


def persist_assistant_exchange(
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
