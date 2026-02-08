"""
Persistence sink tests for Discussion AI quality metrics.
"""

from __future__ import annotations

from app.services.discussion_ai import quality_metrics as qm


class FakeRedis:
    def __init__(self):
        self._hashes = {}
        self._sorted_sets = {}

    def hgetall(self, key):
        bucket = self._hashes.get(key, {})
        return {k.encode("utf-8"): str(v).encode("utf-8") for k, v in bucket.items()}

    def hincrby(self, key, field, amount):
        bucket = self._hashes.setdefault(key, {})
        current = int(bucket.get(field, 0))
        updated = current + int(amount)
        bucket[field] = updated
        return updated

    def delete(self, key):
        self._hashes.pop(key, None)
        self._sorted_sets.pop(key, None)
        return 1

    def hset(self, key, field, value):
        bucket = self._hashes.setdefault(key, {})
        bucket[field] = int(value)
        return 1

    def expire(self, key, seconds):
        # TTL behavior is not needed for unit tests.
        _ = (key, seconds)
        return True

    def zadd(self, key, mapping):
        sorted_set = self._sorted_sets.setdefault(key, {})
        for member, score in mapping.items():
            sorted_set[str(member)] = float(score)
        return 1

    def zrangebyscore(self, key, min_score, max_score):
        sorted_set = self._sorted_sets.get(key, {})
        items = [
            (member, score)
            for member, score in sorted_set.items()
            if float(min_score) <= score <= float(max_score)
        ]
        items.sort(key=lambda x: x[1])
        return [member.encode("utf-8") for member, _ in items]


def test_metrics_persist_to_redis_when_available(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(qm, "_get_redis_client", lambda: fake)

    collector = qm.DiscussionAIMetricsCollector(
        log_every_n_turns=0,
        enable_persistence=True,
        redis_key="test:discussion_ai_metrics:persist",
    )
    collector.reset()

    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=True,
        clarification_first_detected=False,
        recency_requested=True,
        recency_filter_applied=True,
        stage_transition_expected=True,
        stage_transition_success=True,
    )

    snap = collector.snapshot()
    assert snap["storage_backend"] == "redis"
    assert snap["turns_total"] == 1
    assert snap["direct_search_tool_calls_total"] == 1
    assert snap["recency_filter_applied_total"] == 1
    assert snap["stage_transition_success_total"] == 1

    collector.reset()
    snap_after_reset = collector.snapshot()
    assert snap_after_reset["storage_backend"] == "memory"
    assert snap_after_reset["turns_total"] == 0


def test_metrics_fallback_to_memory_when_redis_unavailable(monkeypatch):
    monkeypatch.setattr(qm, "_get_redis_client", lambda: None)

    collector = qm.DiscussionAIMetricsCollector(
        log_every_n_turns=0,
        enable_persistence=True,
        redis_key="test:discussion_ai_metrics:fallback",
    )
    collector.reset()

    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=False,
        clarification_first_detected=True,
        recency_requested=False,
        recency_filter_applied=False,
        stage_transition_expected=False,
        stage_transition_success=False,
    )

    snap = collector.snapshot()
    assert snap["storage_backend"] == "memory"
    assert snap["turns_total"] == 1
    assert snap["direct_search_clarification_first_total"] == 1


def test_metrics_history_from_redis(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(qm, "_get_redis_client", lambda: fake)

    collector = qm.DiscussionAIMetricsCollector(
        log_every_n_turns=0,
        enable_persistence=True,
        redis_key="test:discussion_ai_metrics:history",
    )
    collector.reset()

    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=True,
        clarification_first_detected=False,
        recency_requested=True,
        recency_filter_applied=True,
        stage_transition_expected=True,
        stage_transition_success=True,
    )

    history = collector.history(hours=1, limit=10)
    assert len(history) >= 1
    latest = history[-1]
    assert latest["storage_backend"] == "redis"
    assert latest["turns_total"] >= 1
    assert latest["bucket_start_epoch"] > 0


def test_metrics_history_aggregation(monkeypatch):
    fake = FakeRedis()
    monkeypatch.setattr(qm, "_get_redis_client", lambda: fake)

    times = iter([1000, 1120, 1300])
    monkeypatch.setattr(qm.time, "time", lambda: next(times))

    collector = qm.DiscussionAIMetricsCollector(
        log_every_n_turns=0,
        enable_persistence=True,
        redis_key="test:discussion_ai_metrics:aggregate",
    )
    collector.reset()

    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=True,
        clarification_first_detected=False,
        recency_requested=False,
        recency_filter_applied=False,
        stage_transition_expected=True,
        stage_transition_success=True,
    )
    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=False,
        clarification_first_detected=True,
        recency_requested=True,
        recency_filter_applied=True,
        stage_transition_expected=False,
        stage_transition_success=False,
    )

    history = collector.history(hours=1, limit=10, aggregate_minutes=5)
    assert len(history) == 1
    point = history[0]
    assert point["storage_backend"] == "redis"
    assert point["turns_total"] == 2
    assert point["direct_search_intents_total"] == 2
    assert point["direct_search_tool_calls_total"] == 1
    assert point["direct_search_clarification_first_total"] == 1
    assert point["recency_intents_total"] == 1
    assert point["recency_filter_applied_total"] == 1
    assert point["stage_transition_expected_total"] == 1
    assert point["stage_transition_success_total"] == 1
    assert point["bucket_span_seconds"] == 300
