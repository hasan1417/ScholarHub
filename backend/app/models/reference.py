from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Integer, Float
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

class Reference(Base):
    __tablename__ = "references"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Optional link to a paper; a reference can exist in user's library without attachment
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id", ondelete="CASCADE"), nullable=True)
    # Owner of this reference (user library)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    title = Column(String(500), nullable=False)
    authors = Column(ARRAY(String))
    year = Column(Integer)
    doi = Column(String(255))
    url = Column(String(1000))
    source = Column(String(100))
    journal = Column(String(500))
    abstract = Column(Text)

    is_open_access = Column(Boolean, default=False)
    pdf_url = Column(String(1000))

    status = Column(String(50), default="pending")  # pending, ingested, analyzed
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), nullable=True)

    # Analysis fields
    summary = Column(Text)
    key_findings = Column(ARRAY(String))
    methodology = Column(Text)
    limitations = Column(ARRAY(String))
    relevance_score = Column(Float)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    project_links = relationship("ProjectReference", back_populates="reference", cascade="all, delete-orphan")
    paper_links = relationship("PaperReference", back_populates="reference", cascade="all, delete-orphan")
    discovery_results = relationship("ProjectDiscoveryResult", back_populates="reference")
    paper = relationship("ResearchPaper", back_populates="references_rel")
    document = relationship("Document")
    owner = relationship("User")
    chunks = relationship("DocumentChunk", back_populates="reference")
