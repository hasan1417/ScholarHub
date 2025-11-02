from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

class PaperVersion(Base):
    __tablename__ = "paper_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id"), nullable=False)
    version_number = Column(String(50), nullable=False)  # Changed to string for semantic versioning
    title = Column(String(255), nullable=False)
    content = Column(Text)  # Plain text content
    content_json = Column(JSONB)  # Rich text content in TipTap JSON format
    abstract = Column(Text)
    keywords = Column(Text)
    references = Column(Text)
    
    # Version metadata
    change_summary = Column(Text)  # What changed in this version
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"))  # Who created this version
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    paper = relationship("ResearchPaper", back_populates="versions")
    created_by_user = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<PaperVersion(paper_id={self.paper_id}, version={self.version_number})>"
