from typing import Optional, Tuple, Dict, Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import Project, User
from app.services.subscription_service import SubscriptionService
from app.api.utils.openrouter_keys import try_decrypt_openrouter_key


def _resolve_user_key(
    user: User,
    *,
    error_detail: str,
    log_context: str,
) -> Tuple[Optional[str], Optional[str]]:
    return try_decrypt_openrouter_key(
        user.openrouter_api_key,
        error_detail=error_detail,
        log_context=log_context,
    )


def resolve_openrouter_key_for_user(db: Session, user: User) -> Dict[str, Any]:
    subscription = SubscriptionService.get_or_create_subscription(db, user.id)
    is_byok = subscription.tier_id == "byok"

    user_key, user_warning = _resolve_user_key(
        user,
        error_detail="Your OpenRouter API key is invalid. Please re-enter it in Settings.",
        log_context=f"user {user.id}",
    )

    if is_byok:
        if user_warning:
            return {
                "api_key": None,
                "source": "current_user",
                "warning": user_warning,
                "error_detail": user_warning,
                "error_status": 400,
            }
        if not user_key:
            return {
                "api_key": None,
                "source": "current_user",
                "warning": None,
                "error_detail": "No OpenRouter API key configured. Add your key in Settings.",
                "error_status": 402,
            }
        return {
            "api_key": user_key,
            "source": "current_user",
            "warning": None,
            "error_detail": None,
        "error_status": None,
        }

    warning = user_warning
    if user_key:
        return {
            "api_key": user_key,
            "source": "current_user",
            "warning": warning,
            "error_detail": None,
        "error_status": None,
        }

    if SubscriptionService.allows_server_key(db, user.id) and settings.OPENROUTER_API_KEY:
        return {
            "api_key": settings.OPENROUTER_API_KEY,
            "source": "server",
            "warning": warning,
            "error_detail": None,
            "error_status": None,
        }

    return {
        "api_key": None,
        "source": "none",
        "warning": warning,
        "error_detail": "No API key available. Add your OpenRouter key or upgrade to Pro.",
        "error_status": 402,
    }


def resolve_openrouter_key_for_project(
    db: Session,
    current_user: User,
    project: Project,
    *,
    use_owner_key_for_team: bool = False,
) -> Dict[str, Any]:
    subscription = SubscriptionService.get_or_create_subscription(db, current_user.id)
    is_byok = subscription.tier_id == "byok"

    user_key, user_warning = _resolve_user_key(
        current_user,
        error_detail="Your OpenRouter API key is invalid. Please re-enter it in Settings.",
        log_context=f"user {current_user.id}",
    )

    if is_byok:
        if user_warning:
            return {
                "api_key": None,
                "source": "current_user",
                "warning": user_warning,
                "error_detail": user_warning,
                "error_status": 400,
            }
        if not user_key:
            return {
                "api_key": None,
                "source": "current_user",
                "warning": None,
                "error_detail": "No OpenRouter API key configured. Add your key in Settings.",
                "error_status": 402,
            }
        return {
            "api_key": user_key,
            "source": "current_user",
            "warning": None,
            "error_detail": None,
            "error_status": None,
        }

    warning = user_warning
    if user_key:
        return {
            "api_key": user_key,
            "source": "current_user",
            "warning": warning,
            "error_detail": None,
            "error_status": None,
        }

    # Priority: owner key (if enabled) > server key
    # Check owner key first if project owner has enabled sharing
    if use_owner_key_for_team:
        owner = db.query(User).filter(User.id == project.created_by).first()
        if owner and owner.openrouter_api_key:
            owner_key, owner_warning = _resolve_user_key(
                owner,
                error_detail="Project owner OpenRouter API key is invalid. Please re-enter it in Settings.",
                log_context=f"project owner {owner.id}",
            )
            if owner_key:
                return {
                    "api_key": owner_key,
                    "source": "project_owner",
                    "warning": warning or owner_warning,
                    "error_detail": None,
                    "error_status": None,
                }
            if owner_warning:
                return {
                    "api_key": None,
                    "source": "project_owner",
                    "warning": warning or owner_warning,
                    "error_detail": owner_warning,
                    "error_status": 400,
                }

    # Fall back to server key for all non-BYOK tiers
    if SubscriptionService.allows_server_key(db, current_user.id) and settings.OPENROUTER_API_KEY:
        return {
            "api_key": settings.OPENROUTER_API_KEY,
            "source": "server",
            "warning": warning,
            "error_detail": None,
            "error_status": None,
        }

    return {
        "api_key": None,
        "source": "none",
        "warning": warning,
        "error_detail": "No API key available. Add your OpenRouter key or ask the project owner to enable key sharing.",
        "error_status": 402,
    }
