from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

import enum
import uuid


class ProjectReferenceStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProjectReferenceOrigin(str, enum.Enum):
    UNKNOWN = "unknown"
    MANUAL_DISCOVERY = "manual_discovery"
    AUTO_DISCOVERY = "auto_discovery"
    MANUAL_ADD = "manual_add"
    IMPORT = "import"
    UPLOAD = "upload"


class ProjectReference(Base):
    __tablename__ = "project_references"
    __table_args__ = (
        UniqueConstraint("project_id", "reference_id", name="uq_project_reference"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    reference_id = Column(UUID(as_uuid=True), ForeignKey("references.id", ondelete="CASCADE"), nullable=False)
    status = Column(
        Enum(
            ProjectReferenceStatus,
            name="projectreferencestatus",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=ProjectReferenceStatus.PENDING,
        nullable=False,
    )
    origin = Column(
        Enum(
            ProjectReferenceOrigin,
            name="projectreferenceorigin",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=ProjectReferenceOrigin.UNKNOWN.value,
    )
    discovery_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_discovery_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Track which discussion channel added this reference (for channel context)
    added_via_channel_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_discussion_channels.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Track who added this reference (user who triggered add_to_library or manual add)
    added_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    annotations = Column(JSONB, default=dict)
    confidence = Column(Float)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="references")
    reference = relationship("Reference", back_populates="project_links")
    decider = relationship("User", foreign_keys=[decided_by])
    added_by = relationship("User", foreign_keys=[added_by_user_id])
    discovery_run = relationship("ProjectDiscoveryRun", back_populates="promoted_references")
    added_via_channel = relationship("ProjectDiscussionChannel", foreign_keys=[added_via_channel_id])
    embedding = relationship("PaperEmbedding", back_populates="project_reference", uselist=False, cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<ProjectReference(project_id={self.project_id}, reference_id={self.reference_id}, status={self.status})>"
