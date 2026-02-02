"""
Server-side search results cache.

Stores search results in Redis to prevent client-supplied data from being trusted.
This mitigates prompt injection attacks via crafted paper titles/abstracts.
"""

import json
import logging
from typing import Any, Dict, List, Optional

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Cache TTL: 1 hour (search results are ephemeral)
SEARCH_CACHE_TTL_SECONDS = 3600

# Redis key prefix
SEARCH_CACHE_PREFIX = "search_results:"


def _get_redis_client() -> Optional[redis.Redis]:
    """Get Redis client for search cache."""
    try:
        return redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
        )
    except Exception as e:
        logger.warning(f"Failed to connect to Redis for search cache: {e}")
        return None


def store_search_results(search_id: str, papers: List[Dict[str, Any]]) -> bool:
    """Store search results in Redis.

    Args:
        search_id: Unique search session ID
        papers: List of paper dicts from search

    Returns:
        True if stored successfully, False otherwise
    """
    if not search_id or not papers:
        return False

    client = _get_redis_client()
    if not client:
        logger.warning("Redis not available - search results not cached")
        return False

    try:
        key = f"{SEARCH_CACHE_PREFIX}{search_id}"
        client.setex(key, SEARCH_CACHE_TTL_SECONDS, json.dumps(papers))
        logger.info(f"Cached {len(papers)} search results for search_id={search_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to cache search results: {e}")
        return False


def get_search_results(search_id: str) -> Optional[List[Dict[str, Any]]]:
    """Retrieve search results from Redis.

    Args:
        search_id: Search session ID to look up

    Returns:
        List of paper dicts if found, None otherwise
    """
    if not search_id:
        return None

    client = _get_redis_client()
    if not client:
        return None

    try:
        key = f"{SEARCH_CACHE_PREFIX}{search_id}"
        raw = client.get(key)
        if not raw:
            logger.debug(f"No cached results for search_id={search_id}")
            return None

        papers = json.loads(raw)
        logger.info(f"Retrieved {len(papers)} cached results for search_id={search_id}")
        return papers
    except Exception as e:
        logger.error(f"Failed to retrieve cached search results: {e}")
        return None


def delete_search_results(search_id: str) -> bool:
    """Delete search results from cache.

    Args:
        search_id: Search session ID to delete

    Returns:
        True if deleted, False otherwise
    """
    if not search_id:
        return False

    client = _get_redis_client()
    if not client:
        return False

    try:
        key = f"{SEARCH_CACHE_PREFIX}{search_id}"
        client.delete(key)
        return True
    except Exception as e:
        logger.error(f"Failed to delete cached search results: {e}")
        return False
