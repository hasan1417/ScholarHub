"""
Subscription API endpoints.

Provides endpoints for:
- GET /subscription/me - Get current user's subscription and usage
- GET /subscription/tiers - List available subscription tiers
- POST /subscription/change-tier - Admin: change a user's tier
"""

from uuid import UUID
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.user import User
from app.schemas.subscription import (
    SubscriptionMeResponse,
    SubscriptionTierListResponse,
    SubscriptionTierResponse,
    UserSubscriptionResponse,
    UsageResponse,
    ChangeTierRequest,
    ChangeTierResponse,
)
from app.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/me", response_model=SubscriptionMeResponse)
def get_my_subscription(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get current user's subscription info, limits, and usage.
    """
    subscription = SubscriptionService.get_or_create_subscription(db, current_user.id)
    usage = SubscriptionService.get_or_create_usage(db, current_user.id)
    limits = SubscriptionService.get_user_limits(db, current_user.id)
    resource_counts = SubscriptionService.get_resource_counts(db, current_user.id)

    tier_name = subscription.tier.name if subscription.tier else "Free"

    return SubscriptionMeResponse(
        subscription=UserSubscriptionResponse(
            id=subscription.id,
            tier_id=subscription.tier_id,
            tier_name=tier_name,
            status=subscription.status,
            current_period_start=subscription.current_period_start,
            current_period_end=subscription.current_period_end,
            limits=limits,
            usage=UsageResponse(
                period_year=usage.period_year,
                period_month=usage.period_month,
                discussion_ai_calls=usage.discussion_ai_calls,
                paper_discovery_searches=usage.paper_discovery_searches,
            ),
            created_at=subscription.created_at,
            updated_at=subscription.updated_at,
        ),
        resource_counts=resource_counts,
    )


@router.get("/tiers", response_model=SubscriptionTierListResponse)
def list_subscription_tiers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List all available subscription tiers.
    """
    tiers = SubscriptionService.list_active_tiers(db)

    return SubscriptionTierListResponse(
        tiers=[
            SubscriptionTierResponse(
                id=tier.id,
                name=tier.name,
                price_monthly_cents=tier.price_monthly_cents,
                limits=tier.limits,
                is_active=tier.is_active,
            )
            for tier in tiers
        ]
    )


@router.post("/change-tier", response_model=ChangeTierResponse)
def change_user_tier(
    request: ChangeTierRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Change a user's subscription tier.

    Note: This is an admin-only endpoint in production.
    For now, users can only change their own tier (for testing).
    """
    # In production, add admin check here
    # For testing, allow users to change their own tier
    if request.user_id != current_user.id:
        # TODO: Add admin role check
        # For now, only allow self-changes
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only change your own subscription tier"
        )

    try:
        subscription = SubscriptionService.change_user_tier(
            db, request.user_id, request.tier_id
        )
        logger.info(
            f"User {current_user.id} changed tier for {request.user_id} to {request.tier_id}"
            + (f" - Reason: {request.reason}" if request.reason else "")
        )
        return ChangeTierResponse(
            success=True,
            message=f"Successfully changed tier to {request.tier_id}",
            new_tier_id=subscription.tier_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/usage")
def get_current_usage(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get current month's usage for the authenticated user.
    """
    usage = SubscriptionService.get_or_create_usage(db, current_user.id)
    limits = SubscriptionService.get_user_limits(db, current_user.id)

    return {
        "period_year": usage.period_year,
        "period_month": usage.period_month,
        "usage": {
            "discussion_ai_calls": {
                "current": usage.discussion_ai_calls,
                "limit": limits.get("discussion_ai_calls", 0),
            },
            "editor_ai_calls": {
                "current": usage.editor_ai_calls,
                "limit": limits.get("editor_ai_calls", 0),
            },
            "paper_discovery_searches": {
                "current": usage.paper_discovery_searches,
                "limit": limits.get("paper_discovery_searches", 0),
            },
        },
        "resource_counts": SubscriptionService.get_resource_counts(db, current_user.id),
    }
