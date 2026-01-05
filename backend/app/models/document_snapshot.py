from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey, LargeBinary
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class DocumentSnapshot(Base):
    """
    Stores periodic snapshots of document state for Overleaf-style history feature.

    Yjs binary state is stored directly, allowing reconstruction of any historical state.
    Materialized text is stored for quick diff computation without re-materializing.
    """
    __tablename__ = "document_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id", ondelete="CASCADE"), nullable=False)

    # Yjs state - binary encoded via Y.encodeStateAsUpdate()
    yjs_state = Column(LargeBinary, nullable=False)

    # Materialized LaTeX text for quick access and diff computation
    materialized_text = Column(Text, nullable=True)

    # Snapshot metadata
    snapshot_type = Column(String(20), nullable=False, default="auto")  # 'auto', 'manual', 'restore'
    label = Column(String(255), nullable=True)  # Optional user-provided label

    # Authorship
    created_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Sequence tracking for timeline navigation
    sequence_number = Column(Integer, nullable=False)

    # Size tracking for UI display
    text_length = Column(Integer, nullable=True)

    # Relationships
    paper = relationship("ResearchPaper", backref="snapshots")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self):
        return f"<DocumentSnapshot(paper_id={self.paper_id}, seq={self.sequence_number}, type={self.snapshot_type})>"
