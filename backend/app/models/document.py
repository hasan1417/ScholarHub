from sqlalchemy import Column, String, Text, DateTime, Boolean, ForeignKey, Enum, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid
import enum

class DocumentStatus(str, enum.Enum):
    UPLOADING = "uploading"
    PROCESSING = "processing"
    PROCESSED = "processed"
    FAILED = "failed"

class DocumentType(str, enum.Enum):
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    RESEARCH_PAPER = "research_paper"  # For papers created from scratch
    UNKNOWN = "unknown"  # For unrecognized document types

class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # File information
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255), nullable=False)
    file_path = Column(String(500), nullable=False)
    file_size = Column(Integer)  # in bytes
    mime_type = Column(String(100))
    file_hash = Column(String(64), nullable=False)  # SHA-256 hash for duplicate detection
    
    # Document type and status
    document_type = Column(Enum(DocumentType), nullable=False)
    status = Column(Enum(DocumentStatus), default=DocumentStatus.UPLOADING)
    
    # Content extraction
    extracted_text = Column(Text)
    page_count = Column(Integer)
    
    # Metadata
    title = Column(String(500))
    abstract = Column(Text)
    authors = Column(Text)  # JSON array or comma-separated
    publication_year = Column(Integer)
    journal = Column(String(500))
    doi = Column(String(255))
    
    # Relationships
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id"))  # Optional: can exist without being part of a paper
    
    # AI Processing
    is_processed_for_ai = Column(Boolean, default=False)
    processed_at = Column(DateTime(timezone=True))
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    owner = relationship("User", back_populates="documents")
    paper = relationship("ResearchPaper", back_populates="documents")
    chunks = relationship("DocumentChunk", back_populates="document")  # Removed cascade to avoid pgvector issues
    tags = relationship("DocumentTag", back_populates="document")  # Removed cascade to avoid pgvector issues

    def __repr__(self):
        return f"<Document(id={self.id}, filename='{self.filename}', type={self.document_type})>"
