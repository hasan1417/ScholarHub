from sqlalchemy import Column, String, ForeignKey, Enum, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid
import enum

class PaperRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    EDITOR = "editor"
    REVIEWER = "reviewer"
    VIEWER = "viewer"

class PaperMember(Base):
    __tablename__ = "paper_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    paper_id = Column(UUID(as_uuid=True), ForeignKey("research_papers.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    role = Column(Enum(PaperRole), default=PaperRole.VIEWER, nullable=False)
    status = Column(String(20), default="invited")  # invited, accepted, declined
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    invited_at = Column(DateTime(timezone=True), server_default=func.now())
    joined_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships
    paper = relationship("ResearchPaper", back_populates="members")
    user = relationship("User", back_populates="paper_memberships", foreign_keys=[user_id])
    inviter = relationship("User", foreign_keys=[invited_by])

    def __repr__(self):
        return f"<PaperMember(paper_id={self.paper_id}, user_id={self.user_id}, role={self.role}, status={self.status})>"
