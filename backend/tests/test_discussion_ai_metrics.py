"""
Quality metrics tests for Discussion AI policy/routing behavior.
"""

import os
import sys
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockChannel:
    def __init__(self):
        self.id = "metrics-channel"
        self.name = "Metrics Channel"
        self.ai_memory = None


class MockDB:
    def commit(self):
        return None

    def rollback(self):
        return None


class MockAIService:
    def __init__(self):
        self.default_model = "gpt-5-mini"


class StubToolOrchestrator:
    def __new__(cls, responses):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        class _Stub(ToolOrchestrator):
            def __init__(self, ai_service, db, planned_responses):
                super().__init__(ai_service, db)
                self._planned_responses = list(planned_responses)

            def _call_ai_with_tools(self, messages, ctx):
                if self._planned_responses:
                    return self._planned_responses.pop(0)
                return {"content": "", "tool_calls": []}

        return _Stub(MockAIService(), MockDB(), responses)


def test_metrics_collector_rates():
    from app.services.discussion_ai.quality_metrics import DiscussionAIMetricsCollector

    collector = DiscussionAIMetricsCollector(log_every_n_turns=0, enable_persistence=False)
    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=True,
        clarification_first_detected=True,
        recency_requested=True,
        recency_filter_applied=True,
        stage_transition_expected=True,
        stage_transition_success=True,
    )
    collector.record_turn(
        direct_search_intent=True,
        search_tool_called=False,
        clarification_first_detected=False,
        recency_requested=False,
        recency_filter_applied=False,
        stage_transition_expected=False,
        stage_transition_success=False,
    )

    snap = collector.snapshot()
    assert snap["turns_total"] == 2
    assert snap["direct_search_intents_total"] == 2
    assert snap["direct_search_tool_calls_total"] == 1
    assert snap["direct_search_clarification_first_total"] == 1
    assert snap["recency_intents_total"] == 1
    assert snap["recency_filter_applied_total"] == 1
    assert snap["stage_transition_expected_total"] == 1
    assert snap["stage_transition_success_total"] == 1
    assert snap["direct_search_tool_call_rate"] == 0.5
    assert snap["clarification_first_rate_for_direct_search"] == 0.5
    assert snap["recency_filter_compliance_rate"] == 1.0
    assert snap["stage_transition_success_rate"] == 1.0


def test_orchestrator_records_metrics_for_direct_search_fallback():
    from app.services.discussion_ai.quality_metrics import DiscussionAIMetricsCollector

    orchestrator = StubToolOrchestrator(
        responses=[{"content": "Do you want OA-only papers?", "tool_calls": []}]
    )
    orchestrator._quality_metrics = DiscussionAIMetricsCollector(log_every_n_turns=0, enable_persistence=False)

    channel = MockChannel()
    channel.ai_memory = {
        "facts": {
            "research_topic": "social media and academic performance among university students",
        },
        "research_state": {
            "stage": "exploring",
            "stage_confidence": 0.6,
            "stage_history": [],
        },
    }
    ctx = {
        "channel": channel,
        "user_message": "Can you find me some recent papers on this topic?",
        "user_role": "admin",
        "is_owner": True,
        "reasoning_mode": False,
        "conversation_history": [],
    }
    messages = [{"role": "user", "content": ctx["user_message"]}]

    def fake_execute(name, orch, run_ctx, args):
        return {
            "status": "success",
            "action": {"type": "search_results", "payload": {"query": args.get("query")}},
        }

    with patch.object(orchestrator, "_save_ai_memory", side_effect=lambda ch, mem: setattr(ch, "ai_memory", mem)), patch.object(
        orchestrator, "update_memory_after_exchange", return_value=None
    ), patch.object(orchestrator._tool_registry, "execute", side_effect=fake_execute):
        result = orchestrator._execute_with_tools(messages, ctx)

    assert result["tools_called"] == ["search_papers"]
    snap = orchestrator._quality_metrics.snapshot()
    assert snap["turns_total"] == 1
    assert snap["direct_search_intents_total"] == 1
    assert snap["direct_search_tool_calls_total"] == 1
    assert snap["direct_search_clarification_first_total"] == 1
    assert snap["recency_intents_total"] == 1
    assert snap["recency_filter_applied_total"] == 1
    assert snap["stage_transition_expected_total"] == 1
    assert snap["stage_transition_success_total"] == 1
