from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List

from app.core.config import settings


logger = logging.getLogger(__name__)

DISCUSSION_AI_METRICS_REDIS_KEY = "discussion_ai_quality_metrics:v1"
DISCUSSION_AI_METRICS_REDIS_BUCKET_INDEX_KEY = f"{DISCUSSION_AI_METRICS_REDIS_KEY}:bucket_index"
DISCUSSION_AI_METRICS_BUCKET_SECONDS = 60

_redis_client = None
_redis_initialized = False


def _get_redis_client():
    """Get Redis client, initializing lazily."""
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
    except Exception as exc:
        logger.info("Discussion AI metrics using in-memory fallback (Redis unavailable): %s", exc)
        _redis_client = None
    return _redis_client


@dataclass
class DiscussionAIMetricsCollector:
    """Thread-safe in-process counters for Discussion AI quality signals."""

    log_every_n_turns: int = 25
    enable_persistence: bool = True
    redis_key: str = DISCUSSION_AI_METRICS_REDIS_KEY
    _lock: Lock = field(default_factory=Lock, init=False, repr=False)
    _process_turn_counter: int = field(default=0, init=False, repr=False)
    _counts: Dict[str, int] = field(
        default_factory=lambda: {
            "turns_total": 0,
            "direct_search_intents_total": 0,
            "direct_search_tool_calls_total": 0,
            "direct_search_clarification_first_total": 0,
            "recency_intents_total": 0,
            "recency_filter_applied_total": 0,
            "stage_transition_expected_total": 0,
            "stage_transition_success_total": 0,
        },
        init=False,
        repr=False,
    )

    def record_turn(
        self,
        *,
        direct_search_intent: bool,
        search_tool_called: bool,
        clarification_first_detected: bool,
        recency_requested: bool,
        recency_filter_applied: bool,
        stage_transition_expected: bool,
        stage_transition_success: bool,
    ) -> None:
        deltas = {
            "turns_total": 1,
            "direct_search_intents_total": 1 if direct_search_intent else 0,
            "direct_search_tool_calls_total": 1 if (direct_search_intent and search_tool_called) else 0,
            "direct_search_clarification_first_total": 1 if (direct_search_intent and clarification_first_detected) else 0,
            "recency_intents_total": 1 if recency_requested else 0,
            "recency_filter_applied_total": 1 if (recency_requested and recency_filter_applied) else 0,
            "stage_transition_expected_total": 1 if stage_transition_expected else 0,
            "stage_transition_success_total": 1 if (stage_transition_expected and stage_transition_success) else 0,
        }

        persisted = self._increment_redis_counts(deltas)
        if not persisted:
            self._increment_in_memory(deltas)

        with self._lock:
            self._process_turn_counter += 1
            if self.log_every_n_turns > 0 and self._process_turn_counter % self.log_every_n_turns == 0:
                logger.info("[PolicyMetrics] %s", json.dumps(self.snapshot()))

    def snapshot(self) -> Dict[str, float]:
        redis_counts = self._read_redis_counts()
        if redis_counts is not None:
            return self._snapshot_from_counts(redis_counts, storage_backend="redis")
        with self._lock:
            return self._snapshot_from_counts(dict(self._counts), storage_backend="memory")

    def history(
        self,
        *,
        hours: int = 24,
        limit: int = 120,
        aggregate_minutes: int = 1,
    ) -> List[Dict[str, float]]:
        """Return time-bucketed historical snapshots from the persistence sink."""
        if hours <= 0 or limit <= 0 or aggregate_minutes <= 0:
            return []
        if not self.enable_persistence:
            return []
        client = _get_redis_client()
        if not client:
            return []

        now = int(time.time())
        start = now - (hours * 3600)
        try:
            bucket_keys = client.zrangebyscore(
                DISCUSSION_AI_METRICS_REDIS_BUCKET_INDEX_KEY,
                start,
                now,
            )
            history_points_raw: List[Dict[str, int]] = []
            for key_raw in bucket_keys:
                key = key_raw.decode("utf-8") if isinstance(key_raw, bytes) else str(key_raw)
                raw = client.hgetall(key) or {}
                if not raw:
                    continue
                parsed: Dict[str, int] = {}
                for field, value in raw.items():
                    field_str = field.decode("utf-8") if isinstance(field, bytes) else str(field)
                    value_str = value.decode("utf-8") if isinstance(value, bytes) else str(value)
                    parsed[field_str] = int(value_str)
                parsed["bucket_start_epoch"] = int(parsed.get("bucket_start_epoch", 0))
                parsed["bucket_key"] = key
                history_points_raw.append(parsed)
            if aggregate_minutes > 1:
                history_points_raw = self._aggregate_history_points(
                    history_points_raw,
                    aggregate_minutes=aggregate_minutes,
                )
            # Keep only the most recent entries after optional aggregation.
            history_points_raw = history_points_raw[-limit:]
            history_points: List[Dict[str, float]] = []
            for parsed in history_points_raw:
                point = self._snapshot_from_counts(parsed, storage_backend="redis")
                point["bucket_key"] = str(parsed.get("bucket_key", ""))
                point["bucket_start_epoch"] = int(parsed.get("bucket_start_epoch", 0))
                if "bucket_span_seconds" in parsed:
                    point["bucket_span_seconds"] = int(parsed["bucket_span_seconds"])
                history_points.append(point)
            return history_points
        except Exception as exc:
            logger.debug("Failed to load metrics history from Redis: %s", exc)
            return []

    def reset(self) -> None:
        with self._lock:
            for key in self._counts:
                self._counts[key] = 0
            self._process_turn_counter = 0
        if self.enable_persistence:
            client = _get_redis_client()
            if client:
                try:
                    client.delete(self.redis_key)
                except Exception as exc:
                    logger.debug("Failed to reset Redis metrics key: %s", exc)

    def snapshot_unlocked(self) -> Dict[str, float]:
        return self._snapshot_from_counts(dict(self._counts), storage_backend="memory")

    def _snapshot_from_counts(self, counts: Dict[str, int], storage_backend: str) -> Dict[str, float]:
        for key in self._counts:
            counts.setdefault(key, 0)
        direct_intents = max(1, counts["direct_search_intents_total"])
        recency_intents = max(1, counts["recency_intents_total"])
        stage_expected = max(1, counts["stage_transition_expected_total"])
        counts["direct_search_tool_call_rate"] = round(
            counts["direct_search_tool_calls_total"] / direct_intents, 4
        )
        counts["clarification_first_rate_for_direct_search"] = round(
            counts["direct_search_clarification_first_total"] / direct_intents, 4
        )
        counts["recency_filter_compliance_rate"] = round(
            counts["recency_filter_applied_total"] / recency_intents, 4
        )
        counts["stage_transition_success_rate"] = round(
            counts["stage_transition_success_total"] / stage_expected, 4
        )
        counts["storage_backend"] = storage_backend
        return counts

    def _increment_in_memory(self, deltas: Dict[str, int]) -> None:
        with self._lock:
            for key, delta in deltas.items():
                if delta:
                    self._counts[key] = self._counts.get(key, 0) + int(delta)

    def _increment_redis_counts(self, deltas: Dict[str, int]) -> bool:
        if not self.enable_persistence:
            return False
        client = _get_redis_client()
        if not client:
            return False
        try:
            for key, delta in deltas.items():
                if delta:
                    client.hincrby(self.redis_key, key, int(delta))
            self._increment_redis_bucket(client, deltas)
            return True
        except Exception as exc:
            logger.debug("Failed to persist metrics to Redis: %s", exc)
            return False

    def _read_redis_counts(self) -> Dict[str, int] | None:
        if not self.enable_persistence:
            return None
        client = _get_redis_client()
        if not client:
            return None
        try:
            raw = client.hgetall(self.redis_key) or {}
            if not raw:
                return None
            parsed: Dict[str, int] = {}
            for key, value in raw.items():
                key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
                value_str = value.decode("utf-8") if isinstance(value, bytes) else str(value)
                parsed[key_str] = int(value_str)
            return parsed
        except Exception as exc:
            logger.debug("Failed to read metrics from Redis: %s", exc)
            return None

    def _increment_redis_bucket(self, client, deltas: Dict[str, int]) -> None:
        bucket_start = int(time.time() // DISCUSSION_AI_METRICS_BUCKET_SECONDS) * DISCUSSION_AI_METRICS_BUCKET_SECONDS
        bucket_key = f"{self.redis_key}:bucket:{bucket_start}"
        for key, delta in deltas.items():
            if delta:
                client.hincrby(bucket_key, key, int(delta))
        client.hset(bucket_key, "bucket_start_epoch", bucket_start)
        # Keep each bucket for 30 days to support long-window charts.
        client.expire(bucket_key, 30 * 24 * 3600)
        client.zadd(DISCUSSION_AI_METRICS_REDIS_BUCKET_INDEX_KEY, {bucket_key: bucket_start})
        client.expire(DISCUSSION_AI_METRICS_REDIS_BUCKET_INDEX_KEY, 30 * 24 * 3600)

    def _aggregate_history_points(
        self,
        points: List[Dict[str, int]],
        *,
        aggregate_minutes: int,
    ) -> List[Dict[str, int]]:
        interval_seconds = aggregate_minutes * 60
        grouped: Dict[int, Dict[str, int]] = {}
        for point in points:
            bucket_start = int(point.get("bucket_start_epoch", 0))
            grouped_start = (bucket_start // interval_seconds) * interval_seconds
            agg = grouped.setdefault(grouped_start, {"bucket_start_epoch": grouped_start})
            for key in self._counts:
                agg[key] = int(agg.get(key, 0)) + int(point.get(key, 0))
            agg["bucket_key"] = f"{self.redis_key}:aggregate:{aggregate_minutes}m:{grouped_start}"
            agg["bucket_span_seconds"] = interval_seconds
        return [grouped[k] for k in sorted(grouped.keys())]


_GLOBAL_COLLECTOR = DiscussionAIMetricsCollector()


def get_discussion_ai_metrics_collector() -> DiscussionAIMetricsCollector:
    return _GLOBAL_COLLECTOR
