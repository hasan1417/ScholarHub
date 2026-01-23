from sqlalchemy import Column, String, Text, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from app.database import Base

import uuid


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    slug = Column(String(300), nullable=True, index=True)  # URL-friendly slug
    short_id = Column(String(12), nullable=True, unique=True, index=True)  # Short unique ID for URLs
    idea = Column(Text)
    keywords = Column(ARRAY(String))
    scope = Column(Text)
    status = Column(String(50), default="active")
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    discovery_preferences = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))

    owner = relationship("User", back_populates="owned_projects")
    members = relationship("ProjectMember", back_populates="project", cascade="all, delete-orphan")
    papers = relationship("ResearchPaper", back_populates="project")
    references = relationship("ProjectReference", back_populates="project", cascade="all, delete-orphan")
    meetings = relationship("Meeting", back_populates="project", cascade="all, delete-orphan")
    sync_sessions = relationship("ProjectSyncSession", back_populates="project", cascade="all, delete-orphan")
    ai_artifacts = relationship("AIArtifact", back_populates="project", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="project", cascade="all, delete-orphan")
    discovery_runs = relationship(
        "ProjectDiscoveryRun",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    discovery_results = relationship(
        "ProjectDiscoveryResult",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    discussion_messages = relationship(
        "ProjectDiscussionMessage",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    discussion_channels = relationship(
        "ProjectDiscussionChannel",
        back_populates="project",
        cascade="all, delete-orphan",
    )
    discussion_tasks = relationship(
        "ProjectDiscussionTask",
        back_populates="project",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, title='{self.title}')>"
