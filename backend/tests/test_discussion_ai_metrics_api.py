"""
Unit tests for Discussion AI metrics collector snapshot/reset logic.

Note: The API endpoints use FastAPI dependency injection (get_current_user),
so we test the underlying collector directly rather than calling the endpoint
functions without their required dependencies.
"""

from app.services.discussion_ai.quality_metrics import get_discussion_ai_metrics_collector


def test_collector_snapshot_after_record():
    collector = get_discussion_ai_metrics_collector()
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

    snapshot = collector.snapshot()
    assert snapshot["turns_total"] == 1
    assert snapshot["direct_search_intents_total"] == 1


def test_collector_reset():
    collector = get_discussion_ai_metrics_collector()
    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=True,
        clarification_first_detected=False,
        recency_requested=False,
        recency_filter_applied=False,
        stage_transition_expected=False,
        stage_transition_success=False,
    )

    collector.reset()
    snapshot = collector.snapshot()
    assert snapshot["turns_total"] == 0


def test_collector_history_returns_list():
    collector = get_discussion_ai_metrics_collector()
    collector.reset()
    # history() should always return a list (possibly empty without Redis)
    result = collector.history(hours=1, limit=10, aggregate_minutes=1)
    assert isinstance(result, list)
