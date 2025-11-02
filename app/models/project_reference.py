from sqlalchemy import Column, ForeignKey, Enum, DateTime, Float, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

import enum
import uuid


class ProjectReferenceStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProjectReference(Base):
    __tablename__ = "project_references"
    __table_args__ = (UniqueConstraint("project_id", "reference_id", name="uq_project_reference"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    reference_id = Column(UUID(as_uuid=True), ForeignKey("references.id", ondelete="CASCADE"), nullable=False)
    status = Column(Enum(ProjectReferenceStatus), default=ProjectReferenceStatus.PENDING, nullable=False)
    confidence = Column(Float)
    decided_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    decided_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    project = relationship("Project", back_populates="references")
    reference = relationship("Reference", back_populates="project_links")
    decider = relationship("User")

    def __repr__(self) -> str:
        return f"<ProjectReference(project_id={self.project_id}, reference_id={self.reference_id}, status={self.status})>"
