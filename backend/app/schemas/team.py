from pydantic import BaseModel, UUID4, EmailStr
from typing import Optional
from datetime import datetime
from enum import Enum


class PaperRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    VIEWER = "viewer"


class TeamInviteRequest(BaseModel):
    email: EmailStr
    role: Optional[PaperRole] = PaperRole.VIEWER


class TeamInviteResponse(BaseModel):
    message: str
    team_member_id: UUID4
    status: str


class TeamMemberResponse(BaseModel):
    id: UUID4
    user_id: UUID4
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    role: str
    status: str
    joined_at: Optional[datetime] = None
    is_owner: bool = False

    class Config:
        from_attributes = True


class TeamMemberCreate(BaseModel):
    user_id: UUID4
    role: PaperRole = PaperRole.VIEWER


class TeamMemberUpdate(BaseModel):
    role: PaperRole
