from __future__ import annotations

from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, and_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload
from datetime import datetime

from app.api.deps import get_current_user
from app.database import get_db
from app.models import Project, ProjectMember, ProjectRole, User, ResearchPaper, ProjectReference
from app.services.activity_feed import record_project_activity, preview_text
from app.schemas.project import (
    ProjectCreate,
    ProjectDetail,
    ProjectList,
    ProjectMemberCreate,
    ProjectMemberResponse,
    ProjectMemberSummary,
    ProjectMemberUpdate,
    ProjectSummary,
    ProjectUpdate,
    PendingProjectInvitationList,
    PendingProjectInvitation,
)


router = APIRouter()


def _get_project(db: Session, project_id: UUID) -> Project:
    project = (
        db.query(Project)
        .options(joinedload(Project.members).joinedload(ProjectMember.user))
        .filter(Project.id == project_id)
        .first()
    )
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    return project


def _require_project_access(db: Session, project: Project, user: User) -> ProjectMember | None:
    if project.created_by == user.id:
        return None
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
    return membership


def _ensure_project_manager(db: Session, project: Project, user: User) -> None:
    """Ensure the caller can manage project membership or destructive actions."""

    if project.created_by == user.id:
        return

    membership = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == user.id,
            ProjectMember.status == "accepted",
        )
        .first()
    )
    if not membership or membership.role != ProjectRole.ADMIN:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")


@router.post("/", response_model=ProjectSummary, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = Project(
        title=payload.title,
        idea=payload.idea,
        keywords=payload.keywords,
        scope=payload.scope,
        status=payload.status or "active",
        created_by=current_user.id,
    )
    db.add(project)
    db.flush()

    # Owner membership entry
    membership = ProjectMember(
        project_id=project.id,
        user_id=current_user.id,
        role=ProjectRole.ADMIN,
        status="accepted",
    )
    db.add(membership)
    db.flush()  # Flush so record_project_activity can find the member

    # Record project creation activity
    record_project_activity(
        db=db,
        project=project,
        actor=current_user,
        event_type="project.created",
        payload={
            "category": "project",
            "action": "created",
            "project_title": preview_text(project.title, 160) if project.title else None,
        },
    )

    db.commit()
    db.refresh(project)
    # Return without members - they're not needed for create response
    return ProjectSummary(
        id=project.id,
        title=project.title,
        idea=project.idea,
        keywords=project.keywords,
        scope=project.scope,
        status=project.status,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        discovery_preferences=project.discovery_preferences,
    )


@router.get("/", response_model=ProjectList)
def list_projects(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = (
        db.query(Project)
        .options(joinedload(Project.members).joinedload(ProjectMember.user))
        .outerjoin(ProjectMember, Project.id == ProjectMember.project_id)
        .filter(
            or_(
                Project.created_by == current_user.id,
                and_(
                    ProjectMember.user_id == current_user.id,
                    ProjectMember.status == "accepted",
                ),
            )
        )
        .distinct()
        .order_by(Project.updated_at.desc())
    )

    total = query.count()
    projects = query.offset(skip).limit(limit).all()
    summaries: List[ProjectSummary] = []

    for project in projects:
        if project.created_by == current_user.id:
            role = ProjectRole.ADMIN.value
            user_status = "accepted"
        else:
            membership = next(
                (member for member in project.members if member.user_id == current_user.id),
                None,
            )
            role = membership.role.value if membership else None
            user_status = membership.status if membership else None

        # Build member summaries with user info
        member_summaries = []
        for member in project.members:
            if member.user:
                member_summaries.append(ProjectMemberSummary(
                    id=member.id,
                    user_id=member.user_id,
                    role=member.role,
                    status=member.status,
                    first_name=member.user.first_name,
                    last_name=member.user.last_name,
                    email=member.user.email,
                ))

        # Count papers and references
        paper_count = db.query(ResearchPaper).filter(ResearchPaper.project_id == project.id).count()
        reference_count = db.query(ProjectReference).filter(ProjectReference.project_id == project.id).count()

        summary = ProjectSummary(
            id=project.id,
            title=project.title,
            idea=project.idea,
            keywords=project.keywords,
            scope=project.scope,
            status=project.status,
            created_by=project.created_by,
            created_at=project.created_at,
            updated_at=project.updated_at,
            discovery_preferences=project.discovery_preferences,
            current_user_role=role,
            current_user_status=user_status,
            members=member_summaries,
            paper_count=paper_count,
            reference_count=reference_count,
        )
        summaries.append(summary)

    return ProjectList(projects=summaries, total=total, skip=skip, limit=limit)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    _require_project_access(db, project, current_user)
    db.refresh(project)
    detail = ProjectDetail.model_validate(project, from_attributes=True)
    detail.members = [
        ProjectMemberResponse.model_validate(member, from_attributes=True)
        for member in project.members
    ]
    return detail


@router.put("/{project_id}", response_model=ProjectSummary)
def update_project(
    project_id: UUID,
    payload: ProjectUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    _require_project_access(db, project, current_user)
    _ensure_project_manager(db, project, current_user)

    update_data = payload.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(project, field, value)

    if update_data:
        record_project_activity(
            db=db,
            project=project,
            actor=current_user,
            event_type="project.updated",
            payload={
                "category": "project",
                "action": "updated",
                "updated_fields": sorted(update_data.keys()),
                "project_title": preview_text(project.title, 160) if project.title else None,
            },
        )

    db.commit()
    db.refresh(project)
    # Return without members - they're not needed for update response
    return ProjectSummary(
        id=project.id,
        title=project.title,
        idea=project.idea,
        keywords=project.keywords,
        scope=project.scope,
        status=project.status,
        created_by=project.created_by,
        created_at=project.created_at,
        updated_at=project.updated_at,
        discovery_preferences=project.discovery_preferences,
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    _ensure_project_manager(db, project, current_user)
    db.delete(project)
    db.commit()
    return None


@router.post("/{project_id}/members", response_model=ProjectMemberResponse, status_code=status.HTTP_201_CREATED)
def add_project_member(
    project_id: UUID,
    payload: ProjectMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    _ensure_project_manager(db, project, current_user)

    # Get invited user info for activity recording
    invited_user = db.query(User).filter(User.id == payload.user_id).first()

    membership = ProjectMember(
        project_id=project.id,
        user_id=payload.user_id,
        role=payload.role,
        status="invited",
        invited_by=current_user.id,
    )
    db.add(membership)

    # Record member invited activity
    invited_user_name = None
    if invited_user:
        parts = [p.strip() for p in [invited_user.first_name or "", invited_user.last_name or ""] if p]
        invited_user_name = " ".join(parts) if parts else invited_user.email

    record_project_activity(
        db=db,
        project=project,
        actor=current_user,
        event_type="member.invited",
        payload={
            "category": "member",
            "action": "invited",
            "invited_user_id": str(payload.user_id),
            "invited_user_name": invited_user_name,
            "invited_user_email": invited_user.email if invited_user else None,
            "role": payload.role.value,
        },
    )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Member already exists") from exc
    db.refresh(membership)
    return ProjectMemberResponse.model_validate(membership, from_attributes=True)


@router.patch("/{project_id}/members/{member_id}", response_model=ProjectMemberResponse)
def update_project_member(
    project_id: UUID,
    member_id: UUID,
    payload: ProjectMemberUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    _ensure_project_manager(db, project, current_user)

    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.id == member_id, ProjectMember.project_id == project.id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    membership.role = payload.role
    db.commit()
    db.refresh(membership)
    return ProjectMemberResponse.model_validate(membership, from_attributes=True)


@router.delete("/{project_id}/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_project_member(
    project_id: UUID,
    member_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    _ensure_project_manager(db, project, current_user)

    membership = (
        db.query(ProjectMember)
        .filter(ProjectMember.id == member_id, ProjectMember.project_id == project.id)
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")

    # Get removed user info for activity recording
    removed_user = db.query(User).filter(User.id == membership.user_id).first()
    removed_user_name = None
    if removed_user:
        parts = [p.strip() for p in [removed_user.first_name or "", removed_user.last_name or ""] if p]
        removed_user_name = " ".join(parts) if parts else removed_user.email

    # Record member removed activity
    record_project_activity(
        db=db,
        project=project,
        actor=current_user,
        event_type="member.removed",
        payload={
            "category": "member",
            "action": "removed",
            "removed_user_id": str(membership.user_id),
            "removed_user_name": removed_user_name,
            "removed_user_email": removed_user.email if removed_user else None,
        },
    )

    db.delete(membership)
    db.commit()
    return None


@router.get("/pending/invitations", response_model=PendingProjectInvitationList)
def list_pending_project_invitations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    invitations = (
        db.query(ProjectMember, Project)
        .join(Project, ProjectMember.project_id == Project.id)
        .filter(
            ProjectMember.user_id == current_user.id,
            ProjectMember.status == "invited",
        )
        .all()
    )

    results = []
    for membership, project in invitations:
        inviter = None
        if membership.invited_by:
            inviter_user = db.query(User).filter(User.id == membership.invited_by).first()
            if inviter_user:
                inviter = inviter_user.email or str(inviter_user.id)
        results.append(
            PendingProjectInvitation(
                project_id=project.id,
                project_title=project.title,
                member_id=membership.id,
                role=membership.role,
                invited_at=membership.invited_at,
                invited_by=inviter,
            )
        )

    return PendingProjectInvitationList(invitations=results)


@router.post("/{project_id}/members/{member_id}/accept")
def accept_project_invitation(
    project_id: UUID,
    member_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id,
            ProjectMember.status == "invited",
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    project = db.query(Project).filter(Project.id == project_id).first()

    membership.status = "accepted"
    membership.joined_at = datetime.utcnow()

    # Record member joined activity
    if project:
        record_project_activity(
            db=db,
            project=project,
            actor=current_user,
            event_type="member.joined",
            payload={
                "category": "member",
                "action": "joined",
                "role": membership.role.value,
            },
        )

    db.commit()
    return {"message": "Invitation accepted"}


@router.post("/{project_id}/members/{member_id}/decline")
def decline_project_invitation(
    project_id: UUID,
    member_id: UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    membership = (
        db.query(ProjectMember)
        .filter(
            ProjectMember.id == member_id,
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == current_user.id,
            ProjectMember.status == "invited",
        )
        .first()
    )
    if not membership:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invitation not found")

    project = db.query(Project).filter(Project.id == project_id).first()

    membership.status = "declined"

    # Record member declined activity
    if project:
        record_project_activity(
            db=db,
            project=project,
            actor=current_user,
            event_type="member.declined",
            payload={
                "category": "member",
                "action": "declined",
            },
        )

    db.commit()
    return {"message": "Invitation declined"}
