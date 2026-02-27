import enum
import uuid
from typing import Optional

from sqlalchemy import (
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ProjectDiscoveryRunType(str, enum.Enum):
    MANUAL = "manual"
    AUTO = "auto"


class ProjectDiscoveryRunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ProjectDiscoveryResultStatus(str, enum.Enum):
    PENDING = "pending"
    PROMOTED = "promoted"
    DISMISSED = "dismissed"


class ProjectDiscoveryRun(Base):
    __tablename__ = "project_discovery_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_type = Column(
        Enum(
            ProjectDiscoveryRunType,
            name="projectdiscoveryruntype",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    status = Column(
        Enum(
            ProjectDiscoveryRunStatus,
            name="projectdiscoveryrunstatus",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=ProjectDiscoveryRunStatus.PENDING.value,
    )
    triggered_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    query = Column(Text, nullable=True)
    keywords = Column(ARRAY(String), nullable=True)
    sources = Column(ARRAY(String), nullable=True)
    max_results = Column(Integer, nullable=True)
    relevance_threshold = Column(Float, nullable=True)
    settings_snapshot = Column(JSONB, nullable=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    project = relationship("Project", back_populates="discovery_runs")
    triggered_by_user = relationship("User")
    results = relationship(
        "ProjectDiscoveryResult",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    promoted_references = relationship(
        "ProjectReference",
        back_populates="discovery_run",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return (
            f"<ProjectDiscoveryRun(id={self.id}, project_id={self.project_id}, "
            f"type={self.run_type}, status={self.status})>"
        )


class ProjectDiscoveryResult(Base):
    __tablename__ = "project_discovery_results"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "fingerprint",
            name="uq_project_discovery_result_fingerprint",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_discovery_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("references.id", ondelete="SET NULL"),
        nullable=True,
    )
    status = Column(
        Enum(
            ProjectDiscoveryResultStatus,
            name="projectdiscoveryresultstatus",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        server_default=ProjectDiscoveryResultStatus.PENDING.value,
    )
    source = Column(String(100), nullable=False)
    doi = Column(String(255), nullable=True)
    title = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    authors = Column(ARRAY(String), nullable=True)
    published_year = Column(Integer, nullable=True)
    relevance_score = Column(Float, nullable=True)
    fingerprint = Column(String(128), nullable=False)
    payload = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    promoted_at = Column(DateTime(timezone=True), nullable=True)
    dismissed_at = Column(DateTime(timezone=True), nullable=True)

    run = relationship("ProjectDiscoveryRun", back_populates="results")
    project = relationship("Project", back_populates="discovery_results")
    reference = relationship("Reference", back_populates="discovery_results")

    def __repr__(self) -> str:
        return (
            f"<ProjectDiscoveryResult(id={self.id}, project_id={self.project_id}, "
            f"status={self.status}, source={self.source})>"
        )
