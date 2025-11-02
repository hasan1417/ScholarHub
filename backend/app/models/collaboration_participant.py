from sqlalchemy import Column, String, DateTime, Boolean, ForeignKey, Enum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid
import enum


class ParticipantRole(enum.Enum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"


class CollaborationParticipant(Base):
    __tablename__ = "collaboration_participants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("collaboration_sessions.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(Enum(ParticipantRole), default=ParticipantRole.VIEWER)
    is_active = Column(Boolean, default=True)
    joined_at = Column(DateTime(timezone=True), server_default=func.now())
    last_activity = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    session = relationship("CollaborationSession", back_populates="participants")
    user = relationship("User", back_populates="collaboration_participations")

    def __repr__(self):
        return f"<CollaborationParticipant(id={self.id}, user_id={self.user_id}, role={self.role})>"
