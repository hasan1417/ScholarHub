"""
Paper Embedding model for semantic search.

Stores embeddings for:
- Library papers (project_reference_id set)
- Search cache papers (external_paper_id set)
"""

from __future__ import annotations

import uuid

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    Integer,
    CheckConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

# Import VECTOR from pgvector extension
try:
    from pgvector.sqlalchemy import Vector
    VECTOR = Vector
except ImportError:
    # Fallback for development without pgvector
    from sqlalchemy import Text as VECTOR


class PaperEmbedding(Base):
    """
    Stores paper embeddings for semantic search.

    Two use cases:
    1. Library papers: project_reference_id is set, can find similar in library
    2. Search cache: external_paper_id is set, used for search reranking
    """
    __tablename__ = "paper_embeddings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Reference - one of these should be set
    project_reference_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_references.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )
    external_paper_id = Column(String(255), nullable=True)

    # Content fingerprint
    content_hash = Column(String(64), nullable=False, index=True)
    embedded_text = Column(Text, nullable=False)

    # Embedding vector (384 dims for all-MiniLM-L6-v2)
    embedding = Column(VECTOR(384), nullable=False)

    # Model info
    model_name = Column(String(100), nullable=False, default="all-MiniLM-L6-v2")
    model_version = Column(String(50), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    project_reference = relationship("ProjectReference", back_populates="embedding")

    def __repr__(self) -> str:
        ref = self.project_reference_id or self.external_paper_id
        return f"<PaperEmbedding(id={self.id}, ref={ref}, model={self.model_name})>"


class EmbeddingJob(Base):
    """
    Async job queue for embedding generation.

    Job types:
    - library_paper: Embed a single library paper
    - search_cache: Cache embedding for search result
    - bulk_reindex: Re-embed all papers in a project
    """
    __tablename__ = "embedding_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="ck_embedding_jobs_status"
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Job type and target
    job_type = Column(String(50), nullable=False)  # 'library_paper', 'search_cache', 'bulk_reindex'
    target_id = Column(UUID(as_uuid=True), nullable=True)  # project_reference_id
    project_id = Column(
        UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True
    )

    # Status tracking
    status = Column(String(20), nullable=False, default="pending")
    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=3)
    error_message = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    project = relationship("Project")

    def __repr__(self) -> str:
        return f"<EmbeddingJob(id={self.id}, type={self.job_type}, status={self.status})>"


# Create indexes for efficient queries
Index(
    "ix_paper_embeddings_external_model",
    PaperEmbedding.external_paper_id,
    PaperEmbedding.model_name,
    unique=True,
    postgresql_where=PaperEmbedding.external_paper_id.isnot(None)
)

Index(
    "ix_embedding_jobs_pending",
    EmbeddingJob.status,
    EmbeddingJob.created_at,
    postgresql_where=EmbeddingJob.status == "pending"
)
