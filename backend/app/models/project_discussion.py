from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    ForeignKey,
    Boolean,
    UniqueConstraint,
    CheckConstraint,
    Enum,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

import enum
import uuid

from app.database import Base


class ProjectDiscussionChannel(Base):
    __tablename__ = "project_discussion_channels"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "slug",
            name="uq_discussion_channel_project_slug",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    description = Column(Text)
    is_default = Column(Boolean, nullable=False, server_default=text("false"))
    is_archived = Column(Boolean, nullable=False, server_default=text("false"))
    # Scope configuration: null = project-wide (all resources), or array of types: ["papers", "references", "transcripts"]
    scope = Column(JSONB, nullable=True, server_default=text("NULL"))
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="discussion_channels")
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])
    messages = relationship(
        "ProjectDiscussionMessage",
        back_populates="channel",
        cascade="all, delete-orphan",
    )
    resources = relationship(
        "ProjectDiscussionChannelResource",
        back_populates="channel",
        cascade="all, delete-orphan",
    )
    tasks = relationship(
        "ProjectDiscussionTask",
        back_populates="channel",
        cascade="all, delete-orphan",
    )
    artifact_links = relationship(
        "AIArtifactChannelLink",
        back_populates="channel",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ProjectDiscussionChannel(id={self.id}, project_id={self.project_id}, slug='{self.slug}')>"


class ProjectDiscussionResourceType(str, enum.Enum):
    PAPER = "paper"
    REFERENCE = "reference"
    MEETING = "meeting"


class ProjectDiscussionChannelResource(Base):
    __tablename__ = "project_discussion_channel_resources"
    __table_args__ = (
        CheckConstraint(
            "("  # ensure exactly one target column is populated based on the resource type
            "(resource_type = 'paper' AND paper_id IS NOT NULL AND reference_id IS NULL AND meeting_id IS NULL AND tag IS NULL AND external_url IS NULL)"
            " OR "
            "(resource_type = 'reference' AND reference_id IS NOT NULL AND paper_id IS NULL AND meeting_id IS NULL AND tag IS NULL AND external_url IS NULL)"
            " OR "
            "(resource_type = 'meeting' AND meeting_id IS NOT NULL AND paper_id IS NULL AND reference_id IS NULL AND tag IS NULL AND external_url IS NULL)"
            ")",
            name="ck_discussion_channel_resource_target",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False)
    resource_type = Column(String(16), nullable=False)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id", ondelete="CASCADE"), nullable=True)
    reference_id = Column(UUID(as_uuid=True), ForeignKey("references.id", ondelete="CASCADE"), nullable=True)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="CASCADE"), nullable=True)
    external_url = Column(String(1000), nullable=True)
    tag = Column(String(100), nullable=True)
    details = Column('metadata', JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    added_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    channel = relationship("ProjectDiscussionChannel", back_populates="resources")
    paper = relationship("ResearchPaper")
    reference = relationship("Reference")
    meeting = relationship("Meeting")
    added_by_user = relationship("User", foreign_keys=[added_by])

    def __repr__(self) -> str:
        return (
            f"<ProjectDiscussionChannelResource(id={self.id}, channel_id={self.channel_id}, "
            f"type={self.resource_type})>"
        )


class ProjectDiscussionAttachmentType(str, enum.Enum):
    FILE = "file"
    LINK = "link"
    PAPER = "paper"
    REFERENCE = "reference"
    MEETING = "meeting"


class ProjectDiscussionMessageAttachment(Base):
    __tablename__ = "project_discussion_message_attachments"
    __table_args__ = (
        CheckConstraint(
            "document_id IS NOT NULL OR paper_id IS NOT NULL OR reference_id IS NOT NULL OR "
            "meeting_id IS NOT NULL OR url IS NOT NULL",
            name="ck_discussion_message_attachment_has_target",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    message_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_messages.id", ondelete="CASCADE"), nullable=False)
    attachment_type = Column(String(16), nullable=False)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id", ondelete="SET NULL"), nullable=True)
    reference_id = Column(UUID(as_uuid=True), ForeignKey("references.id", ondelete="SET NULL"), nullable=True)
    meeting_id = Column(UUID(as_uuid=True), ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=True)
    url = Column(String(1000), nullable=True)
    details = Column('metadata', JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    message = relationship("ProjectDiscussionMessage", back_populates="attachments")
    document = relationship("Document")
    paper = relationship("ResearchPaper")
    reference = relationship("Reference")
    meeting = relationship("Meeting")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return f"<ProjectDiscussionMessageAttachment(id={self.id}, message_id={self.message_id}, type={self.attachment_type})>"


class ProjectDiscussionTaskStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectDiscussionTask(Base):
    __tablename__ = "project_discussion_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_messages.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(String(16), nullable=False, server_default=ProjectDiscussionTaskStatus.OPEN.value)
    assignee_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    due_date = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    details = Column('metadata', JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="discussion_tasks")
    channel = relationship("ProjectDiscussionChannel", back_populates="tasks")
    source_message = relationship("ProjectDiscussionMessage", back_populates="tasks")
    assignee = relationship("User", foreign_keys=[assignee_id])
    creator = relationship("User", foreign_keys=[created_by])
    updater = relationship("User", foreign_keys=[updated_by])

    def __repr__(self) -> str:
        return f"<ProjectDiscussionTask(id={self.id}, channel_id={self.channel_id}, status={self.status})>"


class AIArtifactChannelLink(Base):
    __tablename__ = "ai_artifact_channel_links"
    __table_args__ = (
        UniqueConstraint("artifact_id", "channel_id", name="uq_ai_artifact_channel"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artifact_id = Column(UUID(as_uuid=True), ForeignKey("ai_artifacts.id", ondelete="CASCADE"), nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_messages.id", ondelete="SET NULL"), nullable=True)
    linked_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    context_snapshot = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    artifact = relationship("AIArtifact", back_populates="channel_links")
    channel = relationship("ProjectDiscussionChannel", back_populates="artifact_links")
    source_message = relationship("ProjectDiscussionMessage", back_populates="artifact_links")
    linked_by_user = relationship("User", foreign_keys=[linked_by])

    def __repr__(self) -> str:
        return f"<AIArtifactChannelLink(artifact_id={self.artifact_id}, channel_id={self.channel_id})>"


class ProjectDiscussionMessage(Base):
    __tablename__ = "project_discussion_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    parent_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_messages.id", ondelete="CASCADE"), nullable=True)  # For threaded replies
    is_edited = Column(Boolean, default=False)
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="discussion_messages")
    channel = relationship("ProjectDiscussionChannel", back_populates="messages")
    user = relationship("User")
    parent = relationship("ProjectDiscussionMessage", remote_side=[id], backref="replies")
    attachments = relationship(
        "ProjectDiscussionMessageAttachment",
        back_populates="message",
        cascade="all, delete-orphan",
    )
    tasks = relationship(
        "ProjectDiscussionTask",
        back_populates="source_message",
        cascade="all, delete-orphan",
    )
    artifact_links = relationship(
        "AIArtifactChannelLink",
        back_populates="source_message",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectDiscussionMessage(id={self.id}, project_id={self.project_id}, channel_id={self.channel_id})>"
        )


class ProjectDiscussionAssistantExchange(Base):
    __tablename__ = "project_discussion_assistant_exchanges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    question = Column(Text, nullable=False)
    response = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    conversation_state = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project")
    channel = relationship("ProjectDiscussionChannel")
    author = relationship("User")

    def __repr__(self) -> str:
        return f"<ProjectDiscussionAssistantExchange(id={self.id}, channel_id={self.channel_id})>"
