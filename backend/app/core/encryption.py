import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)

ENCRYPTION_PREFIX = "enc:v1:"


def _get_fernet() -> Fernet:
    key = settings.OPENROUTER_KEY_ENCRYPTION_KEY
    if not key:
        raise RuntimeError("OPENROUTER_KEY_ENCRYPTION_KEY is required but not set")
    return Fernet(key)


def encrypt_openrouter_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if value.startswith(ENCRYPTION_PREFIX):
        return value
    token = _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")
    return f"{ENCRYPTION_PREFIX}{token}"


def decrypt_openrouter_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return value
    if not value.startswith(ENCRYPTION_PREFIX):
        # Backward compatibility for existing plaintext values
        return value
    token = value[len(ENCRYPTION_PREFIX):]
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        logger.error("Invalid encrypted OpenRouter API key")
        raise ValueError("Invalid encrypted OpenRouter API key") from exc


def mask_openrouter_key(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    suffix = value[-4:] if len(value) >= 4 else value
    return f"sk-or-...{suffix}"
