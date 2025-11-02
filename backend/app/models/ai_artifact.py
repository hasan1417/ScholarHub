from sqlalchemy import CheckConstraint, Column, DateTime, Enum, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

import enum
import uuid


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
    __table_args__ = (
        CheckConstraint(
            "project_id IS NOT NULL OR paper_id IS NOT NULL",
            name="ck_ai_artifact_has_target",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id", ondelete="CASCADE"), nullable=True)
    type = Column(
        Enum(
            AIArtifactType,
            name="aiartifacttype",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    payload = Column(JSONB, nullable=False, default=dict)
    status = Column(
        Enum(
            AIArtifactStatus,
            name="aiartifactstatus",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=AIArtifactStatus.QUEUED,
        nullable=False,
    )
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="ai_artifacts")
    paper = relationship("ResearchPaper", back_populates="ai_artifacts")
    creator = relationship("User")
    channel_links = relationship(
        "AIArtifactChannelLink",
        back_populates="artifact",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<AIArtifact(id={self.id}, type={self.type}, status={self.status}, "
            f"project_id={self.project_id}, paper_id={self.paper_id})>"
        )
