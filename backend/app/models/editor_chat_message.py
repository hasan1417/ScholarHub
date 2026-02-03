import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class EditorChatMessage(Base):
    __tablename__ = "editor_chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    paper_id = Column(String(length=128), nullable=True)
    project_id = Column(String(length=128), nullable=True)
    role = Column(String(length=20), nullable=False)  # "user" | "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="editor_chat_messages")

    def __repr__(self) -> str:
        return f"<EditorChatMessage(id={self.id}, user_id={self.user_id}, role={self.role})>"
