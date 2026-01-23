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
from app.models import Project, ProjectMember, ProjectRole, User, ResearchPaper, ProjectReference, PendingInvitation
from app.services.activity_feed import record_project_activity, preview_text
from app.services.subscription_service import SubscriptionService
from app.services.email_service import send_project_invitation_email
from app.schemas.pending_invitation import (
    PendingInvitationResponse,
    ProjectInviteRequest,
    ProjectInviteResponse,
)
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
from app.utils.slugify import slugify, generate_short_id


router = APIRouter()


def _is_valid_uuid(val: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


def _parse_short_id(url_id: str) -> str | None:
    """Extract short_id from a URL identifier (slug-shortid or just shortid)."""
    if not url_id or _is_valid_uuid(url_id):
        return None
    if len(url_id) == 8 and url_id.isalnum():
        return url_id
    last_hyphen = url_id.rfind('-')
    if last_hyphen > 0:
        potential = url_id[last_hyphen + 1:]
        if len(potential) == 8 and potential.isalnum():
            return potential
    return None


def _get_project(db: Session, project_id: str | UUID) -> Project:
    """Get project by UUID or slug-shortid format."""
    project = None

    # Try UUID lookup first
    if isinstance(project_id, UUID) or _is_valid_uuid(str(project_id)):
        try:
            uuid_val = project_id if isinstance(project_id, UUID) else UUID(str(project_id))
            project = (
                db.query(Project)
                .options(joinedload(Project.members).joinedload(ProjectMember.user))
                .filter(Project.id == uuid_val)
                .first()
            )
        except (ValueError, AttributeError):
            pass

    # Try short_id lookup
    if not project:
        short_id = _parse_short_id(str(project_id))
        if short_id:
            project = (
                db.query(Project)
                .options(joinedload(Project.members).joinedload(ProjectMember.user))
                .filter(Project.short_id == short_id)
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
    # Check subscription limit for projects
    allowed, current, limit = SubscriptionService.check_resource_limit(
        db, current_user.id, "projects"
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "projects",
                "current": current,
                "limit": limit,
                "message": f"You have reached your project limit ({current}/{limit}). Upgrade to Pro for more projects.",
            },
        )

    project = Project(
        title=payload.title,
        slug=slugify(payload.title) if payload.title else None,
        short_id=generate_short_id(),
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
        role=ProjectRole.OWNER,
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
        slug=project.slug,
        short_id=project.short_id,
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
            slug=project.slug,
            short_id=project.short_id,
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
    project_id: str,
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
    project_id: str,
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
        slug=project.slug,
        short_id=project.short_id,
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
    project_id: str,
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
    project_id: str,
    payload: ProjectMemberCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = _get_project(db, project_id)
    _ensure_project_manager(db, project, current_user)

    # Check subscription limit for collaborators per project
    allowed, current, limit = SubscriptionService.check_resource_limit(
        db, current_user.id, "collaborators_per_project", project_id=project.id
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "collaborators_per_project",
                "current": current,
                "limit": limit,
                "message": f"You have reached your collaborator limit ({current}/{limit}) for this project. Upgrade to Pro for more collaborators.",
            },
        )

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


@router.post("/{project_id}/invite", response_model=ProjectInviteResponse, status_code=status.HTTP_201_CREATED)
def invite_user_to_project(
    project_id: str,
    payload: ProjectInviteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Invite a user to a project by email.

    If the user exists (is registered), create a ProjectMember invitation.
    If the user doesn't exist, create a PendingInvitation that will be fulfilled
    when they register.
    """
    project = _get_project(db, project_id)
    _ensure_project_manager(db, project, current_user)

    # Check subscription limit for collaborators per project
    allowed, current, limit = SubscriptionService.check_resource_limit(
        db, current_user.id, "collaborators_per_project", project_id=project.id
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "limit_exceeded",
                "feature": "collaborators_per_project",
                "current": current,
                "limit": limit,
                "message": f"You have reached your collaborator limit ({current}/{limit}) for this project. Upgrade to Pro for more collaborators.",
            },
        )

    # Check if user is already a member or has a pending invitation
    email_lower = payload.email.lower()

    # Look up user by email
    existing_user = db.query(User).filter(User.email == email_lower).first()

    if existing_user:
        # Check if already a member
        existing_membership = (
            db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == existing_user.id,
            )
            .first()
        )
        if existing_membership:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this project"
            )

        # Create ProjectMember invitation
        membership = ProjectMember(
            project_id=project.id,
            user_id=existing_user.id,
            role=payload.role,
            status="invited",
            invited_by=current_user.id,
        )
        db.add(membership)

        # Record activity
        invited_user_name = None
        parts = [p.strip() for p in [existing_user.first_name or "", existing_user.last_name or ""] if p]
        invited_user_name = " ".join(parts) if parts else existing_user.email

        record_project_activity(
            db=db,
            project=project,
            actor=current_user,
            event_type="member.invited",
            payload={
                "category": "member",
                "action": "invited",
                "invited_user_id": str(existing_user.id),
                "invited_user_name": invited_user_name,
                "invited_user_email": existing_user.email,
                "role": payload.role.value,
            },
        )

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Member already exists") from exc
        db.refresh(membership)

        # Send invitation email to registered user
        inviter_name = " ".join(filter(None, [current_user.first_name, current_user.last_name])) or current_user.email
        try:
            send_project_invitation_email(
                to=existing_user.email,
                project_title=project.title,
                inviter_name=inviter_name,
                role=payload.role.value,
                is_registered=True,
            )
        except Exception:
            pass  # Don't fail the invitation if email fails

        return ProjectInviteResponse(
            success=True,
            message=f"Invitation sent to {existing_user.email}",
            user_exists=True,
            member_id=membership.id,
        )
    else:
        # User doesn't exist - check for existing pending invitation
        existing_pending = (
            db.query(PendingInvitation)
            .filter(
                PendingInvitation.project_id == project.id,
                PendingInvitation.email == email_lower,
            )
            .first()
        )
        if existing_pending:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="An invitation has already been sent to this email"
            )

        # Create PendingInvitation
        pending_invitation = PendingInvitation(
            email=email_lower,
            project_id=project.id,
            role=payload.role.value,
            invited_by=current_user.id,
        )
        db.add(pending_invitation)

        # Record activity for pending invitation
        record_project_activity(
            db=db,
            project=project,
            actor=current_user,
            event_type="member.invited_pending",
            payload={
                "category": "member",
                "action": "invited_pending",
                "invited_email": email_lower,
                "role": payload.role.value,
                "message": "User is not registered yet. They will be added when they sign up.",
            },
        )

        try:
            db.commit()
        except IntegrityError as exc:
            db.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invitation already exists") from exc
        db.refresh(pending_invitation)

        # Send invitation email to unregistered user
        inviter_name = " ".join(filter(None, [current_user.first_name, current_user.last_name])) or current_user.email
        try:
            send_project_invitation_email(
                to=email_lower,
                project_title=project.title,
                inviter_name=inviter_name,
                role=payload.role.value,
                is_registered=False,
            )
        except Exception:
            pass  # Don't fail the invitation if email fails

        return ProjectInviteResponse(
            success=True,
            message=f"Invitation created for {email_lower}. They will be added to the project when they register.",
            user_exists=False,
            pending_invitation_id=pending_invitation.id,
        )


@router.get("/{project_id}/pending-invitations", response_model=List[PendingInvitationResponse])
def get_pending_invitations(
    project_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all pending invitations for unregistered users for this project."""
    project = _get_project(db, project_id)
    _ensure_project_manager(db, project, current_user)

    pending = (
        db.query(PendingInvitation)
        .filter(PendingInvitation.project_id == project.id)
        .order_by(PendingInvitation.created_at.desc())
        .all()
    )
    return [PendingInvitationResponse.model_validate(p, from_attributes=True) for p in pending]


@router.delete("/{project_id}/pending-invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
def cancel_pending_invitation(
    project_id: str,
    invitation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Cancel a pending invitation for an unregistered user."""
    project = _get_project(db, project_id)
    _ensure_project_manager(db, project, current_user)

    pending = (
        db.query(PendingInvitation)
        .filter(
            PendingInvitation.id == invitation_id,
            PendingInvitation.project_id == project.id,
        )
        .first()
    )
    if not pending:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending invitation not found")

    db.delete(pending)
    db.commit()
    return None


@router.patch("/{project_id}/members/{member_id}", response_model=ProjectMemberResponse)
def update_project_member(
    project_id: str,
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
    project_id: str,
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
    project_id: str,
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
    project_id: str,
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
