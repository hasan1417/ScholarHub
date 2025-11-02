from pydantic import BaseModel
from datetime import datetime
from typing import Optional
import uuid


class ChatMessageBase(BaseModel):
    content: str
    message_type: str = "user"


class ChatMessageCreate(ChatMessageBase):
    session_id: uuid.UUID
    user_id: uuid.UUID


class ChatMessageResponse(ChatMessageBase):
    id: uuid.UUID
    session_id: uuid.UUID
    user_id: uuid.UUID
    created_at: datetime
    user_name: Optional[str] = None
    user_email: Optional[str] = None

    class Config:
        from_attributes = True