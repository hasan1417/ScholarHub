from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from uuid import UUID

class TagCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Tag name")
    color: Optional[str] = Field("#3B82F6", pattern=r"^#[0-9A-Fa-f]{6}$", description="Hex color code")

class TagResponse(BaseModel):
    id: UUID
    name: str
    color: str
    created_at: datetime
    
    class Config:
        from_attributes = True
