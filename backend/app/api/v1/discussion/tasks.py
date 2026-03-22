"""Discussion task endpoints: list, create, update, delete tasks."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.api.utils.project_access import ensure_project_member, get_project_or_404
from app.database import get_db
from app.models import (
    ProjectDiscussionMessage,
    ProjectDiscussionTask,
    ProjectDiscussionTaskStatus,
    ProjectRole,
    User,
)
from app.schemas.project_discussion import (
    DiscussionTaskCreate,
    DiscussionTaskResponse,
    DiscussionTaskUpdate,
)
from app.api.v1.discussion_helpers import (
    get_channel_or_404 as _get_channel_or_404,
    serialize_task as _serialize_task,
    parse_task_status as _parse_task_status,
)

router = APIRouter()


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
