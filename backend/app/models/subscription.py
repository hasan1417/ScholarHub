"""
Subscription system models for ScholarHub.

Tables:
- subscription_tiers: Reference table for tier definitions (free, pro)
- user_subscriptions: User subscription records
- usage_tracking: Monthly usage counters per user
"""

from sqlalchemy import Column, String, Boolean, DateTime, Integer, BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
import uuid


class SubscriptionTier(Base):
    """
    Reference table for subscription tier definitions.

    Example tier_id values: 'free', 'pro'
    Limits JSONB example:
    {
        "discussion_ai_calls": 20,
        "paper_discovery_searches": 10,
        "projects": 3,
        "papers_per_project": 10,
        "collaborators_per_project": 2,
        "references_total": 50
    }

    A value of -1 means unlimited.
    """
    __tablename__ = "subscription_tiers"

    id = Column(String(50), primary_key=True)  # 'free', 'pro', etc.
    name = Column(String(100), nullable=False)
    price_monthly_cents = Column(Integer, nullable=False, default=0)
    limits = Column(JSONB, nullable=False, default=dict)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    subscriptions = relationship("UserSubscription", back_populates="tier")

    def __repr__(self):
        return f"<SubscriptionTier(id='{self.id}', name='{self.name}')>"


class UserSubscription(Base):
    """
    User subscription record. One per user.

    Status values: 'active', 'cancelled', 'past_due'
    """
    __tablename__ = "user_subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    tier_id = Column(String(50), ForeignKey("subscription_tiers.id"), nullable=False, default="free")
    status = Column(String(20), nullable=False, default="active")
    current_period_start = Column(DateTime(timezone=True), server_default=func.now())
    current_period_end = Column(DateTime(timezone=True), nullable=True)

    # Future Stripe integration fields
    stripe_customer_id = Column(String(255), nullable=True)
    stripe_subscription_id = Column(String(255), nullable=True)

    # Custom limits override (for special cases / enterprise deals)
    custom_limits = Column(JSONB, nullable=True)

    # Track previous tier when switching to BYOK (to restore when API key removed)
    previous_tier_id = Column(String(50), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="subscription")
    tier = relationship("SubscriptionTier", back_populates="subscriptions")

    def __repr__(self):
        return f"<UserSubscription(user_id={self.user_id}, tier_id='{self.tier_id}')>"

    def get_effective_limits(self) -> dict:
        """Get effective limits, merging tier defaults with custom overrides."""
        base_limits = dict(self.tier.limits) if self.tier and self.tier.limits else {}
        if self.custom_limits:
            base_limits.update(self.custom_limits)
        return base_limits


class UsageTracking(Base):
    """
    Monthly usage tracking per user.

    A new record is created for each user/month combination.
    Usage counters reset at the start of each billing period.
    """
    __tablename__ = "usage_tracking"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    period_year = Column(Integer, nullable=False)
    period_month = Column(Integer, nullable=False)  # 1-12

    # Usage counters (credits: standard models = 1, premium models = 5)
    discussion_ai_calls = Column(Integer, nullable=False, default=0)
    editor_ai_calls = Column(Integer, nullable=False, default=0)
    paper_discovery_searches = Column(Integer, nullable=False, default=0)
    tokens_consumed = Column(BigInteger, nullable=False, default=0)  # internal cost tracking

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relationships
    user = relationship("User", back_populates="usage_records")

    # Unique constraint for one record per user per month
    __table_args__ = (
        UniqueConstraint('user_id', 'period_year', 'period_month', name='uq_usage_user_period'),
    )

    def __repr__(self):
        return f"<UsageTracking(user_id={self.user_id}, period={self.period_year}-{self.period_month:02d})>"
