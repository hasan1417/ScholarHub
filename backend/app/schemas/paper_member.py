from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from app.models.paper_member import PaperRole

class PaperMemberBase(BaseModel):
    paper_id: UUID
    user_id: UUID
    role: PaperRole = PaperRole.VIEWER

class PaperMemberCreate(PaperMemberBase):
    pass

class PaperMemberResponse(PaperMemberBase):
    id: UUID
    
    class Config:
        from_attributes = True
