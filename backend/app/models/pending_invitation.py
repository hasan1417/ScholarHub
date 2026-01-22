"""
Pending Invitation model for inviting unregistered users to projects.
When a user registers with a matching email, they are automatically added to the project.
"""

from sqlalchemy import Column, String, ForeignKey, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import uuid

from app.database import Base


class PendingInvitation(Base):
    __tablename__ = "pending_invitations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Email of the person being invited (not yet registered)
    email = Column(String(255), nullable=False, index=True)

    # Project they're being invited to
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)

    # Role they'll have when they join
    role = Column(String(50), nullable=False, default="viewer")

    # Who sent the invitation
    invited_by = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration

    # Relationships
    project = relationship("Project", backref="pending_invitations")
    inviter = relationship("User", foreign_keys=[invited_by])

    # Composite index for efficient lookups
    __table_args__ = (
        Index("ix_pending_invitations_email_project", "email", "project_id", unique=True),
    )

    def __repr__(self):
        return f"<PendingInvitation {self.email} -> Project {self.project_id} as {self.role}>"
