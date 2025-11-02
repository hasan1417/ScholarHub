from sqlalchemy import Boolean, Column, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

import enum
import uuid


class MeetingStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"


class Meeting(Base):
    __tablename__ = "meetings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    meeting_status_enum = Enum(
        MeetingStatus,
        values_callable=lambda enum_cls: [member.value for member in enum_cls],
        name="meeting_status",
    )

    status = Column(meeting_status_enum, default=MeetingStatus.UPLOADED.value, nullable=False)
    audio_url = Column(String(1000))
    transcript = Column(JSONB)
    summary = Column(String)
    action_items = Column(JSONB)
    session_id = Column(UUID(as_uuid=True), ForeignKey("project_sync_sessions.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="meetings")
    creator = relationship("User")
    session = relationship("ProjectSyncSession", back_populates="recording")

    def __repr__(self) -> str:
        return f"<Meeting(id={self.id}, project_id={self.project_id}, status={self.status})>"


class SyncSessionStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    LIVE = "live"
    ENDED = "ended"
    CANCELLED = "cancelled"


class SyncMessageRole(str, enum.Enum):
    PARTICIPANT = "participant"
    AI = "ai"
    SYSTEM = "system"


status_enum = Enum(SyncSessionStatus, values_callable=lambda enum: [member.value for member in enum])
role_enum = Enum(SyncMessageRole, values_callable=lambda enum: [member.value for member in enum])


class ProjectSyncSession(Base):
    __tablename__ = "project_sync_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    started_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(status_enum, default=SyncSessionStatus.SCHEDULED.value, nullable=False)
    provider = Column(String(100))
    provider_room_id = Column(String(255))
    provider_payload = Column(JSONB)
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="sync_sessions")
    starter = relationship("User")
    messages = relationship("ProjectSyncMessage", back_populates="session", cascade="all, delete-orphan")
    recording = relationship("Meeting", back_populates="session", uselist=False)

    def __repr__(self) -> str:
        return f"<ProjectSyncSession(id={self.id}, project_id={self.project_id}, status={self.status})>"


class ProjectSyncMessage(Base):
    __tablename__ = "project_sync_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("project_sync_sessions.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role = Column(role_enum, default=SyncMessageRole.PARTICIPANT.value, nullable=False)
    content = Column(Text, nullable=False)
    is_command = Column(Boolean, nullable=False, default=False)
    command = Column(String(100))
    payload = Column('metadata', JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ProjectSyncSession", back_populates="messages")
    author = relationship("User")

    def __repr__(self) -> str:
        return f"<ProjectSyncMessage(id={self.id}, session_id={self.session_id}, role={self.role})>"
