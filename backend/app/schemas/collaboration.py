from pydantic import BaseModel, UUID4
from typing import Optional, List
from datetime import datetime
from enum import Enum


class ParticipantRole(str, Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class CollaborationSessionBase(BaseModel):
    paper_id: UUID4
    session_name: Optional[str] = None


class CollaborationSessionCreate(CollaborationSessionBase):
    pass


class CollaborationSessionResponse(CollaborationSessionBase):
    id: UUID4
    is_active: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CollaborationParticipantBase(BaseModel):
    role: ParticipantRole = ParticipantRole.VIEWER


class CollaborationParticipantCreate(CollaborationParticipantBase):
    user_id: UUID4


class CollaborationParticipantResponse(CollaborationParticipantBase):
    id: UUID4
    user_id: UUID4
    is_active: bool
    joined_at: datetime
    last_activity: Optional[datetime] = None
    user_email: Optional[str] = None
    user_name: Optional[str] = None

    class Config:
        from_attributes = True


class CollaborationInviteRequest(BaseModel):
    email: str
    role: Optional[ParticipantRole] = ParticipantRole.VIEWER


class CollaborationMessage(BaseModel):
    type: str
    content: Optional[str] = None
    user_id: Optional[UUID4] = None
    timestamp: Optional[datetime] = None
    metadata: Optional[dict] = None
