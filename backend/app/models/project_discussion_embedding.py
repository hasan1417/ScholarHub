from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base
from sqlalchemy.dialects.postgresql import JSONB


class DiscussionEmbeddingOrigin(str, enum.Enum):
    RESOURCE = "resource"
    MESSAGE = "message"
    TASK = "task"
    ARTIFACT = "artifact"


class ProjectDiscussionEmbedding(Base):
    __tablename__ = "project_discussion_embeddings"
    __table_args__ = (
        UniqueConstraint(
            "origin_type",
            "origin_id",
            name="uq_discussion_embedding_origin",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False)
    origin_type = Column(Enum(DiscussionEmbeddingOrigin, name="discussion_embedding_origin"), nullable=False)
    origin_id = Column(UUID(as_uuid=True), nullable=False)
    text = Column(Text, nullable=False)
    text_signature = Column(String(64), nullable=False)
    embedding = Column(JSONB, nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    stale = Column(Boolean, nullable=False, default=False)

    project = relationship("Project")
    channel = relationship("ProjectDiscussionChannel")

    def __repr__(self) -> str:
        return (
            f"<ProjectDiscussionEmbedding(channel_id={self.channel_id}, origin_type={self.origin_type}, "
            f"origin_id={self.origin_id})>"
        )
