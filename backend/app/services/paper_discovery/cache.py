"""Small async-safe LRU cache implementation used by discovery."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from typing import Any, Optional


class LRUCache:
    """A lock-protected LRU cache with TTL support for async workflows."""

    def __init__(self, max_size: int = 1000, ttl_seconds: float = 3600.0) -> None:
        self._cache: OrderedDict[str, Any] = OrderedDict()
        self._timestamps: dict[str, float] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key not in self._cache:
                return None

            if time.time() - self._timestamps[key] > self._ttl:
                del self._cache[key]
                del self._timestamps[key]
                return None

            self._cache.move_to_end(key)
            return self._cache[key]

    async def set(self, key: str, value: Any) -> None:
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            else:
                if len(self._cache) >= self._max_size:
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]
                    del self._timestamps[oldest]
                self._cache[key] = value
            self._timestamps[key] = time.time()

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()
            self._timestamps.clear()
