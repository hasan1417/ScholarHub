"""
Pydantic schemas for the subscription system.
"""

from pydantic import BaseModel
from typing import Optional, Dict, Any, Literal
from datetime import datetime
from uuid import UUID


# Tier schemas
class SubscriptionTierLimits(BaseModel):
    """Structured limits for a subscription tier."""
    discussion_ai_calls: int = 20
    paper_discovery_searches: int = 10
    projects: int = 3
    papers_per_project: int = 10
    collaborators_per_project: int = 2
    references_total: int = 50


class SubscriptionTierResponse(BaseModel):
    """Response schema for subscription tier info."""
    id: str
    name: str
    price_monthly_cents: int
    limits: Dict[str, Any]
    is_active: bool

    class Config:
        from_attributes = True


class SubscriptionTierListResponse(BaseModel):
    """Response schema for listing available tiers."""
    tiers: list[SubscriptionTierResponse]


# Usage schemas
class UsageResponse(BaseModel):
    """Response schema for current usage stats."""
    period_year: int
    period_month: int
    discussion_ai_calls: int
    paper_discovery_searches: int

    class Config:
        from_attributes = True


# User subscription schemas
class UserSubscriptionResponse(BaseModel):
    """Response schema for user's subscription info."""
    id: UUID
    tier_id: str
    tier_name: str
    status: str
    current_period_start: Optional[datetime] = None
    current_period_end: Optional[datetime] = None
    limits: Dict[str, Any]
    usage: UsageResponse
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class SubscriptionMeResponse(BaseModel):
    """Combined response for /subscription/me endpoint."""
    subscription: UserSubscriptionResponse
    resource_counts: Dict[str, int]  # projects_count, references_count, etc.


# Admin change tier request
class ChangeTierRequest(BaseModel):
    """Request to change a user's tier (admin only)."""
    user_id: UUID
    tier_id: str
    reason: Optional[str] = None


class ChangeTierResponse(BaseModel):
    """Response after changing a user's tier."""
    success: bool
    message: str
    new_tier_id: str


# Limit exceeded response (for 402 errors)
class LimitExceededDetail(BaseModel):
    """Detail schema for 402 Payment Required errors."""
    error: Literal["limit_exceeded"] = "limit_exceeded"
    feature: str
    current: int
    limit: int
    tier: str
    upgrade_url: Optional[str] = None


# Feature usage check result
class FeatureLimitCheck(BaseModel):
    """Result of checking a feature limit."""
    allowed: bool
    current: int
    limit: int
    feature: str


# Resource count check result
class ResourceLimitCheck(BaseModel):
    """Result of checking a resource count limit."""
    allowed: bool
    current: int
    limit: int
    resource: str
