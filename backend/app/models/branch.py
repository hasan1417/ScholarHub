from sqlalchemy import Column, String, DateTime, Text, Boolean, JSON, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class Branch(Base):
    __tablename__ = "branches"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id"), nullable=False)
    parent_branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    status = Column(String(50), default="active")  # active, merged, archived
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    last_commit_message = Column(Text, default="")
    is_main = Column(Boolean, default=False)

    # Relationships
    paper = relationship("ResearchPaper", back_populates="branches")
    author = relationship("User")
    parent_branch = relationship("Branch", remote_side=[id])
    commits = relationship("Commit", back_populates="branch", cascade="all, delete-orphan")
    
    # Self-referential relationship for child branches
    child_branches = relationship("Branch", cascade="all, delete-orphan")


class Commit(Base):
    __tablename__ = "commits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    message = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    content_json = Column(JSON, nullable=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    changes = Column(JSON, nullable=False, default=list)  # Store array of Change objects
    compilation_status = Column(String(20), nullable=False, default="not_compiled")  # success, failed, not_compiled
    pdf_url = Column(Text, nullable=True)
    compile_logs = Column(Text, nullable=True)
    state = Column(String(32), nullable=False, default="draft")  # draft, ready_for_review, published

    # Relationships
    branch = relationship("Branch", back_populates="commits")
    author = relationship("User")


class MergeRequest(Base):
    __tablename__ = "merge_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    target_branch_id = Column(UUID(as_uuid=True), ForeignKey("branches.id"), nullable=False)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(50), default="open")  # open, merged, closed, conflicted
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    author_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    conflicts = Column(JSON, nullable=True)  # Store array of Conflict objects

    # Relationships
    source_branch = relationship("Branch", foreign_keys=[source_branch_id])
    target_branch = relationship("Branch", foreign_keys=[target_branch_id])
    paper = relationship("ResearchPaper")
    author = relationship("User")


class ConflictResolution(Base):
    __tablename__ = "conflict_resolutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merge_request_id = Column(UUID(as_uuid=True), ForeignKey("merge_requests.id"), nullable=False)
    section = Column(String(255), nullable=False)
    source_content = Column(Text)
    target_content = Column(Text)
    resolved_content = Column(Text)
    status = Column(String(50), default="unresolved")  # unresolved, resolved, auto-resolved
    resolution_strategy = Column(String(50), default="manual")  # manual, auto, source-wins, target-wins
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    merge_request = relationship("MergeRequest")
    resolver = relationship("User")
