from sqlalchemy import Column, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base

import uuid


class PaperReference(Base):
    __tablename__ = "paper_references"
    __table_args__ = (UniqueConstraint("paper_id", "reference_id", name="uq_paper_reference"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id", ondelete="CASCADE"), nullable=False)
    reference_id = Column(UUID(as_uuid=True), ForeignKey("references.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    paper = relationship("ResearchPaper", back_populates="reference_links")
    reference = relationship("Reference", back_populates="paper_links")

    def __repr__(self) -> str:
        return f"<PaperReference(paper_id={self.paper_id}, reference_id={self.reference_id})>"
