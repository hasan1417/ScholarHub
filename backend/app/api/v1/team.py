from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import List
import uuid
from datetime import datetime, timedelta

from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.research_paper import ResearchPaper
from app.models.paper_member import PaperMember, PaperRole
from app.models.project_member import ProjectMember
from app.schemas.team import (
    TeamMemberCreate,
    TeamMemberResponse,
    TeamInviteRequest,
    TeamInviteResponse,
    TeamMemberUpdate,
)

router = APIRouter()


@router.post("/papers/{paper_id}/invite", response_model=TeamInviteResponse)
async def invite_team_member(
    paper_id: uuid.UUID,
    invite_data: TeamInviteRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Invite a user to join the paper team"""
    
    # Check if paper exists
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    # Check if current user can invite (owner or admin member)
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.role == PaperRole.ADMIN
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Not authorized to invite team members")
    
    # Find the user to invite
    invitee = db.query(User).filter(User.email == invite_data.email).first()
    if not invitee:
        # Return generic error to prevent user enumeration
        raise HTTPException(status_code=400, detail="Unable to send invitation. The user may not exist or may not be eligible.")

    # Check if already a team member
    existing_member = db.query(PaperMember).filter(
        PaperMember.paper_id == paper_id,
        PaperMember.user_id == invitee.id
    ).first()
    
    if existing_member:
        raise HTTPException(status_code=400, detail="User is already a team member")
    
    assignable_roles = {PaperRole.ADMIN, PaperRole.EDITOR, PaperRole.VIEWER}
    desired_role = invite_data.role or PaperRole.VIEWER
    if desired_role not in assignable_roles:
        raise HTTPException(status_code=400, detail="Invalid role for invitation")

    # If paper belongs to a project, also invite user to the project if not already a member
    if paper.project_id:
        existing_project_member = db.query(ProjectMember).filter(
            ProjectMember.project_id == paper.project_id,
            ProjectMember.user_id == invitee.id
        ).first()

        if not existing_project_member:
            # Map paper role to project role (same roles apply)
            project_role = desired_role.value.lower() if hasattr(desired_role, 'value') else str(desired_role).lower()
            project_member = ProjectMember(
                project_id=paper.project_id,
                user_id=invitee.id,
                role=project_role,
                status="invited",
                invited_by=current_user.id,
            )
            db.add(project_member)

    # Create team member invitation for the paper
    team_member = PaperMember(
        paper_id=paper_id,
        user_id=invitee.id,
        role=desired_role,
        status="invited",  # invited, accepted, declined
        invited_by=current_user.id,
        invited_at=datetime.utcnow()
    )

    db.add(team_member)
    db.commit()
    db.refresh(team_member)

    # TODO: Send email invitation in background
    # background_tasks.add_task(send_team_invitation_email, invitee.email, paper.title, current_user.email)

    return TeamInviteResponse(
        message=f"Invitation sent to {invitee.email}",
        team_member_id=team_member.id,
        status="invited"
    )


@router.get("/papers/{paper_id}/members", response_model=List[TeamMemberResponse])
async def get_team_members(
    paper_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all team members for a paper"""
    
    # Check if user has access to this paper
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Not authorized to view team members")
    
    # Return ONLY DB-backed team members (including owner record if present)
    members: list[TeamMemberResponse] = []
    team_members = db.query(PaperMember).filter(
        PaperMember.paper_id == paper_id,
        PaperMember.status.in_(["accepted", "invited", "declined"])
    ).all()

    # De-duplicate by user_id (guard against accidental duplicates)
    seen_user_ids = set()
    for member in team_members:
        if member.user_id in seen_user_ids:
            continue
        seen_user_ids.add(member.user_id)
        user = db.query(User).filter(User.id == member.user_id).first()
        if not user:
            continue
        role_value = member.role.value if member.role != PaperRole.REVIEWER else PaperRole.VIEWER.value
        members.append(TeamMemberResponse(
            id=member.id,
            user_id=user.id,
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name,
            role=role_value,
            status=member.status,
            joined_at=member.joined_at or member.invited_at,
            is_owner=(member.user_id == paper.owner_id or member.role == PaperRole.OWNER)
        ))

    return members


@router.post("/papers/{paper_id}/members/{member_id}/accept")
async def accept_team_invitation(
    paper_id: uuid.UUID,
    member_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Accept a team invitation"""
    
    # Check if invitation exists and belongs to current user
    member = db.query(PaperMember).filter(
        PaperMember.id == member_id,
        PaperMember.paper_id == paper_id,
        PaperMember.user_id == current_user.id,
        PaperMember.status == "invited"
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    # Accept invitation
    member.status = "accepted"
    member.joined_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Invitation accepted successfully"}


@router.post("/papers/{paper_id}/members/{member_id}/decline")
async def decline_team_invitation(
    paper_id: uuid.UUID,
    member_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Decline a team invitation"""
    
    # Check if invitation exists and belongs to current user
    member = db.query(PaperMember).filter(
        PaperMember.id == member_id,
        PaperMember.paper_id == paper_id,
        PaperMember.user_id == current_user.id,
        PaperMember.status == "invited"
    ).first()
    
    if not member:
        raise HTTPException(status_code=404, detail="Invitation not found")
    
    # Decline invitation
    member.status = "declined"
    db.commit()
    
    return {"message": "Invitation declined successfully"}


@router.delete("/papers/{paper_id}/members/{member_id}")
async def remove_team_member(
    paper_id: uuid.UUID,
    member_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Remove a team member (owner or admin only)"""
    
    # Check if current user can remove members
    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")
    
    if paper.owner_id != current_user.id:
        member = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.role == PaperRole.ADMIN
        ).first()
        if not member:
            raise HTTPException(status_code=403, detail="Not authorized to remove team members")
    
    # Remove team member
    member_to_remove = db.query(PaperMember).filter(
        PaperMember.id == member_id,
        PaperMember.paper_id == paper_id
    ).first()
    
    if not member_to_remove:
        raise HTTPException(status_code=404, detail="Team member not found")
    
    db.delete(member_to_remove)
    db.commit()
    
    return {"message": "Team member removed successfully"}


@router.patch("/papers/{paper_id}/members/{member_id}", response_model=TeamMemberResponse)
async def update_team_member_role(
    paper_id: uuid.UUID,
    member_id: uuid.UUID,
    payload: TeamMemberUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing team member's role (owner or admin only)."""

    paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
    if not paper:
        raise HTTPException(status_code=404, detail="Research paper not found")

    if paper.owner_id != current_user.id:
        manager = db.query(PaperMember).filter(
            PaperMember.paper_id == paper_id,
            PaperMember.user_id == current_user.id,
            PaperMember.role == PaperRole.ADMIN,
            PaperMember.status == "accepted"
        ).first()
        if not manager:
            raise HTTPException(status_code=403, detail="Not authorized to update team members")

    member = db.query(PaperMember).filter(
        PaperMember.id == member_id,
        PaperMember.paper_id == paper_id
    ).first()
    if not member:
        raise HTTPException(status_code=404, detail="Team member not found")

    if member.role == PaperRole.OWNER:
        raise HTTPException(status_code=400, detail="Cannot modify owner role")

    assignable_roles = {PaperRole.ADMIN, PaperRole.EDITOR, PaperRole.VIEWER}
    if payload.role not in assignable_roles:
        raise HTTPException(status_code=400, detail="Invalid role assignment")

    member.role = payload.role
    db.commit()
    db.refresh(member)

    user = db.query(User).filter(User.id == member.user_id).first()
    role_value = member.role.value if member.role != PaperRole.REVIEWER else PaperRole.VIEWER.value

    return TeamMemberResponse(
        id=member.id,
        user_id=member.user_id,
        email=user.email if user else "",
        first_name=user.first_name if user else None,
        last_name=user.last_name if user else None,
        role=role_value,
        status=member.status,
        joined_at=member.joined_at or member.invited_at,
        is_owner=(member.user_id == paper.owner_id or member.role == PaperRole.OWNER)
    )
