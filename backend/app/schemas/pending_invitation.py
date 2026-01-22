"""
Pydantic schemas for pending invitations.
"""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr

from app.models.project_member import ProjectRole


class PendingInvitationBase(BaseModel):
    email: EmailStr
    role: ProjectRole = ProjectRole.VIEWER


class PendingInvitationCreate(PendingInvitationBase):
    pass


class PendingInvitationResponse(PendingInvitationBase):
    id: UUID
    project_id: UUID
    invited_by: Optional[UUID] = None
    created_at: datetime
    expires_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProjectInviteRequest(BaseModel):
    """Request to invite a user (either existing or not) to a project by email."""
    email: EmailStr
    role: ProjectRole = ProjectRole.VIEWER


class ProjectInviteResponse(BaseModel):
    """Response for project invite - could be a member or pending invitation."""
    success: bool
    message: str
    user_exists: bool
    # If user exists, membership info
    member_id: Optional[UUID] = None
    # If user doesn't exist, pending invitation info
    pending_invitation_id: Optional[UUID] = None
