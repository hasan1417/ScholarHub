from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class EditorChatMessageResponse(BaseModel):
    id: UUID
    role: str
    content: str
    author_name: str
    author_id: Optional[UUID] = None
    created_at: datetime

    class Config:
        from_attributes = True
