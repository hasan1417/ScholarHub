from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Integer, BigInteger, LargeBinary, text
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

class ResearchPaper(Base):
    __tablename__ = "research_papers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(255), nullable=False)
    slug = Column(String(300), nullable=True, index=True)  # URL-friendly slug
    short_id = Column(String(12), nullable=True, unique=True, index=True)  # Short unique ID for URLs
    abstract = Column(Text)
    content = Column(Text)  # Plain text content for backward compatibility
    content_json = Column(JSONB)  # Rich text content in TipTap JSON format
    status = Column(String(50), default="draft")  # draft, in_progress, completed, published
    paper_type = Column(String(50), default="research")  # research, review, case_study, etc.
    current_version = Column(String(50), default="1.0")  # Current version number
    format = Column(String(50))  # Editor format (latex, rtf, etc.)
    summary = Column(Text)
    objectives = Column(JSONB, nullable=True, default=list)
    
    # Ownership and collaboration
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    is_public = Column(Boolean, default=False)
    
    # Metadata
    keywords = Column(ARRAY(String))  # Array of keywords
    references = Column(Text)  # Bibliography
    latex_files = Column(JSONB, nullable=True)  # Multi-file LaTeX: {"main.tex": "...", "intro.tex": "..."}
    latex_crdt_state = Column(LargeBinary, nullable=True)
    latex_crdt_rev = Column(BigInteger, nullable=False, default=0)
    latex_crdt_checksum = Column(String(64))
    latex_crdt_synced_at = Column(DateTime(timezone=True))
    editor_ai_context = Column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    
    # Discovery metadata
    year = Column(Integer)  # Publication year
    doi = Column(String(255))  # DOI identifier
    url = Column(String(500))  # External URL
    source = Column(String(50))  # Source of discovery (arxiv, semantic_scholar, etc.)
    authors = Column(ARRAY(String))  # Array of author names
    journal = Column(String(255))  # Journal name
    description = Column(Text)  # Paper description/abstract
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    project = relationship("Project", back_populates="papers")
    owner = relationship("User", back_populates="owned_papers")
    members = relationship("PaperMember", back_populates="paper", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="paper", cascade="all, delete-orphan")
    versions = relationship("PaperVersion", back_populates="paper", cascade="all, delete-orphan")
    collaboration_sessions = relationship("CollaborationSession", back_populates="paper", cascade="all, delete-orphan")
    branches = relationship("Branch", back_populates="paper", cascade="all, delete-orphan")
    references_rel = relationship("Reference", back_populates="paper", cascade="all, delete-orphan")
    reference_links = relationship("PaperReference", back_populates="paper", cascade="all, delete-orphan")
    ai_artifacts = relationship("AIArtifact", back_populates="paper", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<ResearchPaper(id={self.id}, title='{self.title}', owner_id={self.owner_id})>"
