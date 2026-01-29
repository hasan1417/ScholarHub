"""
Subscription service for ScholarHub.

Provides functions for:
- Getting user limits (tier + custom overrides)
- Checking if a feature is within limits
- Incrementing usage counters
- Checking resource counts against limits
"""

from datetime import datetime
from typing import Tuple, Dict, Any, Optional
from uuid import UUID
import logging

from sqlalchemy.orm import Session

from app.models.subscription import SubscriptionTier, UserSubscription, UsageTracking
from app.models import Project, ProjectMember, Reference

logger = logging.getLogger(__name__)

# Default limits for free tier (fallback if DB not seeded)
DEFAULT_FREE_LIMITS = {
    "discussion_ai_calls": 20,
    "paper_discovery_searches": 10,
    "projects": 3,
    "papers_per_project": 10,
    "collaborators_per_project": 2,
    "references_total": 50,
}


class SubscriptionService:
    """Service class for subscription and usage management."""

    @staticmethod
    def get_or_create_subscription(db: Session, user_id: UUID) -> UserSubscription:
        """
        Get user's subscription, creating a free tier subscription if none exists.
        """
        subscription = db.query(UserSubscription).filter(
            UserSubscription.user_id == user_id
        ).first()

        if not subscription:
            # Create free tier subscription for user
            subscription = UserSubscription(
                user_id=user_id,
                tier_id="free",
                status="active",
            )
            db.add(subscription)
            db.commit()
            db.refresh(subscription)
            logger.info(f"Created free tier subscription for user {user_id}")

        return subscription

    @staticmethod
    def get_user_limits(db: Session, user_id: UUID) -> Dict[str, Any]:
        """
        Get effective limits for a user (tier defaults + custom overrides).
        Returns a dict with limit values. -1 means unlimited.
        """
        subscription = SubscriptionService.get_or_create_subscription(db, user_id)

        # Get base limits from tier
        if subscription.tier and subscription.tier.limits:
            limits = dict(subscription.tier.limits)
        else:
            # Fallback to default free limits
            limits = dict(DEFAULT_FREE_LIMITS)

        # Apply custom overrides if present
        if subscription.custom_limits:
            limits.update(subscription.custom_limits)

        return limits

    @staticmethod
    def get_or_create_usage(db: Session, user_id: UUID) -> UsageTracking:
        """
        Get or create the current month's usage record for a user.
        """
        now = datetime.utcnow()
        year = now.year
        month = now.month

        usage = db.query(UsageTracking).filter(
            UsageTracking.user_id == user_id,
            UsageTracking.period_year == year,
            UsageTracking.period_month == month,
        ).first()

        if not usage:
            usage = UsageTracking(
                user_id=user_id,
                period_year=year,
                period_month=month,
                discussion_ai_calls=0,
                paper_discovery_searches=0,
            )
            db.add(usage)
            db.commit()
            db.refresh(usage)
            logger.info(f"Created usage tracking for user {user_id} for {year}-{month:02d}")

        return usage

    @staticmethod
    def check_feature_limit(
        db: Session, user_id: UUID, feature: str
    ) -> Tuple[bool, int, int]:
        """
        Check if a user is within their limit for a monthly-tracked feature.

        Args:
            db: Database session
            user_id: User's UUID
            feature: Feature name (e.g., 'discussion_ai_calls', 'paper_discovery_searches')

        Returns:
            Tuple of (allowed: bool, current_usage: int, limit: int)
            If limit is -1, it means unlimited and allowed is always True.
        """
        limits = SubscriptionService.get_user_limits(db, user_id)
        usage = SubscriptionService.get_or_create_usage(db, user_id)

        limit = limits.get(feature, 0)
        current = getattr(usage, feature, 0)

        # -1 means unlimited
        if limit == -1:
            return (True, current, -1)

        allowed = current < limit
        return (allowed, current, limit)

    @staticmethod
    def increment_usage(
        db: Session, user_id: UUID, feature: str, amount: int = 1
    ) -> UsageTracking:
        """
        Increment a usage counter after a successful action.

        Args:
            db: Database session
            user_id: User's UUID
            feature: Feature name (e.g., 'discussion_ai_calls')
            amount: Amount to increment (default 1)

        Returns:
            Updated UsageTracking record
        """
        usage = SubscriptionService.get_or_create_usage(db, user_id)

        current_value = getattr(usage, feature, 0)
        setattr(usage, feature, current_value + amount)
        db.commit()
        db.refresh(usage)

        logger.debug(f"Incremented {feature} for user {user_id}: {current_value} -> {current_value + amount}")
        return usage

    @staticmethod
    def check_resource_limit(
        db: Session, user_id: UUID, resource: str, project_id: Optional[UUID] = None
    ) -> Tuple[bool, int, int]:
        """
        Check if a user is within their limit for a resource count.

        Args:
            db: Database session
            user_id: User's UUID
            resource: Resource type (e.g., 'projects', 'references_total',
                      'papers_per_project', 'collaborators_per_project')
            project_id: Required for project-specific limits

        Returns:
            Tuple of (allowed: bool, current_count: int, limit: int)
        """
        limits = SubscriptionService.get_user_limits(db, user_id)
        limit = limits.get(resource, 0)

        if limit == -1:
            return (True, 0, -1)

        if resource == "projects":
            # Count projects owned by user + projects where user is a member
            owned_count = db.query(Project).filter(Project.created_by == user_id).count()
            member_count = db.query(ProjectMember).filter(
                ProjectMember.user_id == user_id,
                ProjectMember.status == "accepted"
            ).count()
            # Avoid double-counting if user is both owner and member
            current = max(owned_count, member_count)

        elif resource == "references_total":
            # Count references owned by user
            current = db.query(Reference).filter(Reference.owner_id == user_id).count()

        elif resource == "papers_per_project":
            if not project_id:
                return (True, 0, limit)  # Can't check without project_id
            from app.models import ResearchPaper
            current = db.query(ResearchPaper).filter(
                ResearchPaper.project_id == project_id
            ).count()

        elif resource == "collaborators_per_project":
            if not project_id:
                return (True, 0, limit)
            current = db.query(ProjectMember).filter(
                ProjectMember.project_id == project_id,
                ProjectMember.status == "accepted"
            ).count()

        else:
            # Unknown resource type
            return (True, 0, limit)

        allowed = current < limit
        return (allowed, current, limit)

    @staticmethod
    def get_resource_counts(db: Session, user_id: UUID) -> Dict[str, int]:
        """
        Get current resource counts for a user.

        Returns dict with counts for: projects, references_total
        """
        owned_projects = db.query(Project).filter(Project.created_by == user_id).count()
        references = db.query(Reference).filter(Reference.owner_id == user_id).count()

        return {
            "projects": owned_projects,
            "references_total": references,
        }

    @staticmethod
    def change_user_tier(
        db: Session, user_id: UUID, new_tier_id: str
    ) -> UserSubscription:
        """
        Change a user's subscription tier (admin function).

        Args:
            db: Database session
            user_id: User's UUID
            new_tier_id: New tier ID (e.g., 'free', 'pro')

        Returns:
            Updated UserSubscription
        """
        # Verify tier exists
        tier = db.query(SubscriptionTier).filter(
            SubscriptionTier.id == new_tier_id,
            SubscriptionTier.is_active == True
        ).first()
        if not tier:
            raise ValueError(f"Tier '{new_tier_id}' not found or inactive")

        subscription = SubscriptionService.get_or_create_subscription(db, user_id)
        old_tier = subscription.tier_id
        subscription.tier_id = new_tier_id
        subscription.current_period_start = datetime.utcnow()

        db.commit()
        db.refresh(subscription)

        logger.info(f"Changed user {user_id} tier from '{old_tier}' to '{new_tier_id}'")
        return subscription

    @staticmethod
    def get_tier_by_id(db: Session, tier_id: str) -> Optional[SubscriptionTier]:
        """Get a subscription tier by ID."""
        return db.query(SubscriptionTier).filter(
            SubscriptionTier.id == tier_id
        ).first()

    @staticmethod
    def list_active_tiers(db: Session) -> list[SubscriptionTier]:
        """List all active subscription tiers."""
        return db.query(SubscriptionTier).filter(
            SubscriptionTier.is_active == True
        ).all()

    @staticmethod
    def assign_byok_tier(db: Session, user_id: UUID) -> UserSubscription:
        """
        Assign BYOK tier to a user when they add their API key.
        Saves their previous tier so it can be restored if they remove the key.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Updated UserSubscription
        """
        subscription = SubscriptionService.get_or_create_subscription(db, user_id)

        # Don't change if already on BYOK
        if subscription.tier_id == "byok":
            logger.debug(f"User {user_id} already on BYOK tier")
            return subscription

        # Save current tier before switching
        subscription.previous_tier_id = subscription.tier_id
        subscription.tier_id = "byok"

        db.commit()
        db.refresh(subscription)

        logger.info(f"Assigned BYOK tier to user {user_id} (previous: {subscription.previous_tier_id})")
        return subscription

    @staticmethod
    def remove_byok_tier(db: Session, user_id: UUID) -> UserSubscription:
        """
        Remove BYOK tier from a user when they remove their API key.
        Restores their previous tier.

        Args:
            db: Database session
            user_id: User's UUID

        Returns:
            Updated UserSubscription
        """
        subscription = SubscriptionService.get_or_create_subscription(db, user_id)

        # Only revert if currently on BYOK
        if subscription.tier_id != "byok":
            logger.debug(f"User {user_id} not on BYOK tier, no change needed")
            return subscription

        # Restore previous tier (default to 'free' if none saved)
        previous_tier = subscription.previous_tier_id or "free"
        subscription.tier_id = previous_tier
        subscription.previous_tier_id = None

        db.commit()
        db.refresh(subscription)

        logger.info(f"Removed BYOK tier from user {user_id}, restored to '{previous_tier}'")
        return subscription
