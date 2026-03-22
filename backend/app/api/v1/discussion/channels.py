"""Discussion channel endpoints: WebSocket, CRUD, stats, and channel resources."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
    Response,
    WebSocket,
    WebSocketDisconnect,
)
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
    ProjectDiscussionResourceType,
    ProjectReference,
    Reference,
    ProjectRole,
    ResearchPaper,
    User,
)
from app.schemas.project_discussion import (
    DiscussionChannelCreate,
    DiscussionChannelResourceCreate,
    DiscussionChannelResourceResponse,
    DiscussionChannelSummary,
    DiscussionChannelUpdate,
    DiscussionStats,
)
from app.services.websocket_manager import connection_manager
from app.api.v1.discussion_helpers import (
    slugify as _slugify,
    generate_unique_slug as _generate_unique_slug,
    ensure_default_channel as _ensure_default_channel,
    get_channel_or_404 as _get_channel_or_404,
    serialize_channel as _serialize_channel,
    serialize_resource as _serialize_resource,
    discussion_session_id as _discussion_session_id,
    display_name_for_user as _display_name_for_user,
)

router = APIRouter()

logger = logging.getLogger(__name__)


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

    channel_query = db.query(ProjectDiscussionChannel).filter(
        ProjectDiscussionChannel.project_id == project.id,
        ProjectDiscussionChannel.is_paper_chat.is_(False),
    )
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
