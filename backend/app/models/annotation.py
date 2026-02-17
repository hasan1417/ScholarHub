from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import uuid


class PdfAnnotation(Base):
    __tablename__ = "pdf_annotations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_number = Column(Integer, nullable=False)
    type = Column(String(20), nullable=False)  # "highlight", "note", "underline"
    color = Column(String(7), default="#FFEB3B")  # hex color
    content = Column(Text, nullable=True)  # text note content
    position_data = Column(JSONB, nullable=False)  # {rects: [{x, y, width, height}], ...}
    selected_text = Column(Text, nullable=True)  # the highlighted text
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    document = relationship("Document", backref="annotations")
    user = relationship("User", backref="pdf_annotations")

    def __repr__(self):
        return f"<PdfAnnotation(id={self.id}, type='{self.type}', page={self.page_number})>"
