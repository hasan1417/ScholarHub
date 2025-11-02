from sqlalchemy import Column, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base

class DocumentTag(Base):
    __tablename__ = "document_tags"
    
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id"), primary_key=True)
    tag_id = Column(UUID(as_uuid=True), ForeignKey("tags.id"), primary_key=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    document = relationship("Document", back_populates="tags")
    tag = relationship("Tag", back_populates="document_tags")
    
    def __repr__(self):
        return f"<DocumentTag(document_id={self.document_id}, tag_id={self.tag_id})>"
