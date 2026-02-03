from sqlalchemy import Column, String, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    first_name = Column(String(100))
    last_name = Column(String(100))
    avatar_url = Column(String(500), nullable=True)  # Profile picture URL
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    refresh_token = Column(String(255))  # Stores hashed refresh token
    refresh_token_expires_at = Column(DateTime(timezone=True))  # Refresh token expiration
    refresh_token_last_hash = Column(String(255))
    refresh_token_last_seen_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # OAuth fields
    google_id = Column(String(255), unique=True, nullable=True, index=True)
    auth_provider = Column(String(50), default="local")  # "local" or "google"

    # Email verification tokens
    email_verification_token = Column(String(255), nullable=True)
    email_verification_sent_at = Column(DateTime(timezone=True), nullable=True)

    # Password reset tokens
    password_reset_token = Column(String(255), nullable=True)
    password_reset_sent_at = Column(DateTime(timezone=True), nullable=True)

    # API Keys (user-provided, used instead of system keys)
    openrouter_api_key = Column(String(255), nullable=True)  # User's OpenRouter API key

    # Relationships
    owned_projects = relationship("Project", back_populates="owner", cascade="all, delete-orphan")
    owned_papers = relationship("ResearchPaper", back_populates="owner", cascade="all, delete-orphan")
    project_memberships = relationship("ProjectMember", back_populates="user", foreign_keys="ProjectMember.user_id", cascade="all, delete-orphan")
    paper_memberships = relationship("PaperMember", back_populates="user", foreign_keys="PaperMember.user_id", cascade="all, delete-orphan")
    documents = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    ai_chat_sessions = relationship("AIChatSession", back_populates="user", cascade="all, delete-orphan")
    editor_chat_messages = relationship("EditorChatMessage", back_populates="user", cascade="all, delete-orphan")
    collaboration_participations = relationship("CollaborationParticipant", back_populates="user")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")

    # Subscription relationships
    subscription = relationship("UserSubscription", back_populates="user", uselist=False, cascade="all, delete-orphan")
    usage_records = relationship("UsageTracking", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}')>"
