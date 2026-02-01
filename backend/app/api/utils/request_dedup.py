"""
Request deduplication utilities.

Uses Redis to prevent duplicate request processing within a time window.
"""

import logging
from typing import Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cache for Redis client
_redis_client = None
_redis_initialized = False

# Deduplication settings
DEDUP_TTL_SECONDS = 300  # 5 minutes
DEDUP_KEY_PREFIX = "discussion_dedup:"


def _get_redis_client():
    """Get Redis client, initializing if needed."""
    global _redis_client, _redis_initialized
    if _redis_initialized:
        return _redis_client
    _redis_initialized = True
    try:
        import redis as redis_lib
        client = redis_lib.Redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        client.ping()
        _redis_client = client
    except Exception as e:
        logger.warning(f"Redis not available for deduplication: {e}")
        _redis_client = None
    return _redis_client


def check_and_set_request(
    idempotency_key: str,
    exchange_id: str,
    ttl: int = DEDUP_TTL_SECONDS,
) -> Tuple[bool, Optional[str]]:
    """
    Check if a request with this idempotency key is already being processed.

    Args:
        idempotency_key: Client-provided unique key for this request
        exchange_id: The exchange ID for this request
        ttl: Time-to-live in seconds for the dedup entry

    Returns:
        Tuple of (is_new, existing_exchange_id)
        - (True, None) if this is a new request (key was set)
        - (False, exchange_id) if duplicate (returns existing exchange ID)
    """
    if not idempotency_key:
        return True, None

    client = _get_redis_client()
    if not client:
        # Redis not available - allow request (no dedup)
        return True, None

    cache_key = f"{DEDUP_KEY_PREFIX}{idempotency_key}"

    try:
        # Try to set the key only if it doesn't exist (NX)
        was_set = client.set(cache_key, exchange_id, nx=True, ex=ttl)

        if was_set:
            # New request - key was set
            logger.debug(f"Dedup: New request with key {idempotency_key[:16]}...")
            return True, None
        else:
            # Duplicate - get existing exchange ID
            existing = client.get(cache_key)
            existing_id = existing.decode('utf-8') if existing else None
            logger.info(f"Dedup: Duplicate request detected, key={idempotency_key[:16]}..., existing_exchange={existing_id}")
            return False, existing_id
    except Exception as e:
        logger.warning(f"Dedup check failed: {e}")
        # On error, allow request
        return True, None


def clear_request(idempotency_key: str) -> None:
    """
    Clear a deduplication entry (call on request completion or failure).

    Args:
        idempotency_key: The key to clear
    """
    if not idempotency_key:
        return

    client = _get_redis_client()
    if not client:
        return

    cache_key = f"{DEDUP_KEY_PREFIX}{idempotency_key}"

    try:
        client.delete(cache_key)
        logger.debug(f"Dedup: Cleared key {idempotency_key[:16]}...")
    except Exception as e:
        logger.warning(f"Dedup clear failed: {e}")


def update_request_status(
    idempotency_key: str,
    status: str,
    ttl: int = DEDUP_TTL_SECONDS,
) -> None:
    """
    Update the status stored for an idempotency key.

    Args:
        idempotency_key: The key to update
        status: New status value (e.g., "processing", "completed")
        ttl: Refresh TTL on update
    """
    if not idempotency_key:
        return

    client = _get_redis_client()
    if not client:
        return

    cache_key = f"{DEDUP_KEY_PREFIX}{idempotency_key}"

    try:
        client.set(cache_key, status, ex=ttl)
    except Exception as e:
        logger.warning(f"Dedup status update failed: {e}")
