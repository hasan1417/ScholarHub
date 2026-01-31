import logging
from typing import Optional

from fastapi import HTTPException, status

from app.core.encryption import decrypt_openrouter_key

logger = logging.getLogger(__name__)


def decrypt_openrouter_key_or_400(
    raw_value: Optional[str],
    *,
    error_detail: str,
    log_context: str,
) -> Optional[str]:
    if not raw_value:
        return None
    try:
        return decrypt_openrouter_key(raw_value)
    except ValueError:
        logger.error("Invalid encrypted OpenRouter API key for %s", log_context)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_detail,
        )


def try_decrypt_openrouter_key(
    raw_value: Optional[str],
    *,
    error_detail: str,
    log_context: str,
) -> tuple[Optional[str], Optional[str]]:
    if not raw_value:
        return None, None
    try:
        return decrypt_openrouter_key(raw_value), None
    except ValueError:
        logger.error("Invalid encrypted OpenRouter API key for %s", log_context)
        return None, error_detail
