from sqlalchemy import Column, Enum, ForeignKey, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.database import Base

import enum
import uuid


class AIArtifactTarget(str, enum.Enum):
    PROJECT = "project"
    PAPER = "paper"


class AIArtifactType(str, enum.Enum):
    SUMMARY = "summary"
    LIT_REVIEW = "litReview"
    OUTLINE = "outline"
    DIRECTORY_HELP = "directoryHelp"
    INTENT = "intent"


class AIArtifactStatus(str, enum.Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class AIArtifact(Base):
    __tablename__ = "ai_artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    target_type = Column(Enum(AIArtifactTarget), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    type = Column(Enum(AIArtifactType), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    status = Column(Enum(AIArtifactStatus), default=AIArtifactStatus.QUEUED, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="ai_artifacts", primaryjoin="and_(Project.id==AIArtifact.target_id, AIArtifact.target_type=='project')", viewonly=True)
    paper = relationship("ResearchPaper", back_populates="ai_artifacts", primaryjoin="and_(ResearchPaper.id==AIArtifact.target_id, AIArtifact.target_type=='paper')", viewonly=True)
    creator = relationship("User")

    def __repr__(self) -> str:
        return f"<AIArtifact(id={self.id}, target={self.target_type}:{self.target_id}, type={self.type}, status={self.status})>"
