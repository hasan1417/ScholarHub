"""
Discussion AI behavior contract tests.

These tests validate deterministic policy-first behavior for direct paper search
routing without depending on model phrasing details.
"""

import os
import sys
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class MockChannel:
    def __init__(self):
        self.id = "contract-channel-1"
        self.name = "Contract Test Channel"
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
    """Small wrapper to provide deterministic model responses in tests."""

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


class StubStreamingOpenRouterOrchestrator:
    """Streaming OpenRouter stub with deterministic streamed events per iteration."""

    def __new__(cls, planned_event_sequences):
        from app.services.discussion_ai.openrouter_orchestrator import OpenRouterOrchestrator

        class _Stub(OpenRouterOrchestrator):
            def __init__(self, ai_service, db, planned_events):
                super().__init__(
                    ai_service,
                    db,
                    model="openai/gpt-5-mini",
                    user_api_key="test-openrouter-key",
                )
                self._planned_events = [list(seq) for seq in planned_events]

            async def _call_ai_with_tools_streaming(self, messages, ctx):
                _ = (messages, ctx)
                if self._planned_events:
                    for event in self._planned_events.pop(0):
                        yield event
                else:
                    yield {"type": "result", "content": "", "tool_calls": []}

        return _Stub(MockAIService(), MockDB(), planned_event_sequences)


class TestPolicyDecisionContract:
    def test_direct_search_decision_defaults(self):
        from app.services.discussion_ai.policy import DiscussionPolicy

        policy = DiscussionPolicy()
        decision = policy.build_decision(
            user_message="Can you find me some recent papers on this topic?",
            topic_hint="social media and academic performance",
            search_tool_available=True,
        )

        assert decision.intent == "direct_search"
        assert decision.should_force_tool("search_papers") is True
        assert decision.search is not None
        assert decision.search.count == 5
        assert decision.search.open_access_only is False
        assert "social media and academic performance" in decision.search.query.lower()
        current_year = datetime.now(timezone.utc).year
        assert decision.search.year_from == current_year - 4
        assert decision.search.year_to == current_year

    def test_non_search_message_not_forced(self):
        from app.services.discussion_ai.policy import DiscussionPolicy

        policy = DiscussionPolicy()
        decision = policy.build_decision(
            user_message="Can you explain the difference between precision and recall?",
            topic_hint="",
            search_tool_available=True,
        )

        assert decision.intent == "general"
        assert decision.should_force_tool("search_papers") is False
        assert decision.search is None

    def test_explicit_year_window_is_extracted(self):
        from app.services.discussion_ai.policy import DiscussionPolicy

        policy = DiscussionPolicy()
        decision = policy.build_decision(
            user_message="Find papers on this topic from 2020 to 2023",
            topic_hint="social media and academic performance",
            search_tool_available=True,
        )

        assert decision.search is not None
        assert decision.search.year_from == 2020
        assert decision.search.year_to == 2023

    def test_last_n_years_window_is_extracted(self):
        from app.services.discussion_ai.policy import DiscussionPolicy

        policy = DiscussionPolicy()
        decision = policy.build_decision(
            user_message="Can you find papers from the last 3 years on this topic?",
            topic_hint="topic",
            search_tool_available=True,
        )

        assert decision.search is not None
        current_year = datetime.now(timezone.utc).year
        assert decision.search.year_from == current_year - 2
        assert decision.search.year_to == current_year

    def test_relative_followup_uses_last_search_topic(self):
        from app.services.discussion_ai.policy import DiscussionPolicy

        policy = DiscussionPolicy()
        decision = policy.build_decision(
            user_message="Can you find another 3 papers?",
            topic_hint="",
            last_search_topic="sleep deprivation cognitive function medical residents",
            search_tool_available=True,
        )

        assert decision.intent == "direct_search"
        assert decision.search is not None
        assert decision.search.count == 3
        assert "sleep deprivation cognitive function medical residents" in decision.search.query.lower()

    def test_project_update_intent_blocks_search_tools(self):
        from app.services.discussion_ai.policy import DiscussionPolicy

        policy = DiscussionPolicy()
        decision = policy.build_decision(
            user_message="Please update project keywords to climate adaptation and resilience",
            topic_hint="",
            search_tool_available=True,
        )

        assert decision.intent == "project_update"
        assert decision.action_plan is not None
        assert "search_papers" in decision.action_plan.blocked_tools


class TestRoutingContract:
    def test_direct_search_forces_tool_when_model_returns_text_only(self):
        orchestrator = StubToolOrchestrator(
            responses=[{"content": "Do you want OA-only papers?", "tool_calls": []}]
        )
        channel = MockChannel()
        channel.ai_memory = {
            "facts": {
                "research_topic": "Social media usage and academic performance among university students",
            }
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

        captured_args = {}

        def fake_execute(name, orch, run_ctx, args):
            captured_args.update(args)
            return {"status": "success", "action": {"type": "search_results", "payload": {"query": args.get("query")}}}

        with patch.object(orchestrator, "update_memory_after_exchange", return_value=None), patch.object(
            orchestrator._tool_registry, "execute", side_effect=fake_execute
        ):
            result = orchestrator._execute_with_tools(messages, ctx)

        assert result["tools_called"] == ["search_papers"]
        assert result["message"].startswith("Searching for papers now")
        assert captured_args["count"] == 5
        assert captured_args["limit"] == 5
        assert captured_args["open_access_only"] is False
        assert captured_args["year_from"] is not None
        assert captured_args["year_to"] is not None
        assert "social media usage and academic performance" in captured_args["query"].lower()

    def test_non_search_prompt_does_not_force_search(self):
        orchestrator = StubToolOrchestrator(
            responses=[{"content": "Precision is the share of predicted positives that are correct.", "tool_calls": []}]
        )
        channel = MockChannel()
        channel.ai_memory = {"facts": {}}
        ctx = {
            "channel": channel,
            "user_message": "Can you explain precision vs recall in one paragraph?",
            "user_role": "admin",
            "is_owner": True,
            "reasoning_mode": False,
            "conversation_history": [],
        }
        messages = [{"role": "user", "content": ctx["user_message"]}]

        with patch.object(orchestrator, "update_memory_after_exchange", return_value=None), patch.object(
            orchestrator._tool_registry, "execute"
        ) as execute_mock:
            result = orchestrator._execute_with_tools(messages, ctx)

        execute_mock.assert_not_called()
        assert result["tools_called"] == []
        assert "precision" in result["message"].lower()

    def test_empty_model_message_gets_deterministic_fallback(self):
        orchestrator = StubToolOrchestrator(
            responses=[{"content": "", "tool_calls": []}]
        )
        channel = MockChannel()
        channel.ai_memory = {"facts": {}}
        ctx = {
            "channel": channel,
            "user_message": "My research question is about sleep and cognition.",
            "user_role": "admin",
            "is_owner": True,
            "reasoning_mode": False,
            "conversation_history": [],
        }
        messages = [{"role": "user", "content": ctx["user_message"]}]

        with patch.object(orchestrator, "update_memory_after_exchange", return_value=None):
            result = orchestrator._execute_with_tools(messages, ctx)

        assert "I captured your request:" in result["message"]
        assert "sleep and cognition" in result["message"].lower()

    def test_direct_search_forces_search_even_after_non_search_tool_roundtrip(self):
        orchestrator = StubToolOrchestrator(
            responses=[
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-lib-1",
                            "name": "get_project_references",
                            "arguments": {"limit": 20},
                        }
                    ],
                },
                {"content": "Do you want OA-only papers?", "tool_calls": []},
            ]
        )
        channel = MockChannel()
        channel.ai_memory = {"facts": {"research_topic": "social media and academic performance"}}
        ctx = {
            "channel": channel,
            "user_message": "Can you find me some recent papers on this topic?",
            "user_role": "admin",
            "is_owner": True,
            "reasoning_mode": False,
            "conversation_history": [],
        }
        messages = [{"role": "user", "content": ctx["user_message"]}]

        called_tools = []

        def fake_execute(name, orch, run_ctx, args):
            _ = (orch, run_ctx, args)
            called_tools.append(name)
            if name == "search_papers":
                return {"status": "success", "action": {"type": "search_results", "payload": {}}}
            return {"status": "success", "references": []}

        with patch.object(orchestrator, "update_memory_after_exchange", return_value=None), patch.object(
            orchestrator._tool_registry, "execute", side_effect=fake_execute
        ):
            result = orchestrator._execute_with_tools(messages, ctx)

        assert called_tools == ["get_project_references", "search_papers"]
        assert result["message"].startswith("Searching for papers now")
        assert result["tools_called"] == ["get_project_references", "search_papers"]

    def test_direct_search_forced_for_viewer_with_read_only_tools(self):
        orchestrator = StubToolOrchestrator(
            responses=[{"content": "Do you want OA-only papers?", "tool_calls": []}]
        )
        channel = MockChannel()
        channel.ai_memory = {"facts": {"research_topic": "Topic"}}
        ctx = {
            "channel": channel,
            "user_message": "Can you find me papers on this topic?",
            "user_role": "viewer",
            "is_owner": False,
            "reasoning_mode": False,
            "conversation_history": [],
        }
        messages = [{"role": "user", "content": ctx["user_message"]}]

        captured_args = {}

        def fake_execute(name, orch, run_ctx, args):
            captured_args.update(args)
            return {"action": {"type": "search_results", "payload": {"query": args.get("query")}}}

        with patch.object(orchestrator, "update_memory_after_exchange", return_value=None), patch.object(
            orchestrator._tool_registry, "execute", side_effect=fake_execute
        ):
            result = orchestrator._execute_with_tools(messages, ctx)

        assert result["tools_called"] == ["search_papers"]
        assert captured_args["count"] == 5
        assert captured_args["limit"] == 5
        assert captured_args["open_access_only"] is False

    def test_viewer_tool_filter_excludes_write_actions(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        tools = orchestrator._get_tools_for_user({"user_role": "viewer", "is_owner": False})
        tool_names = {tool.get("function", {}).get("name") for tool in tools}

        assert "search_papers" in tool_names
        assert "get_project_references" in tool_names
        assert "add_to_library" not in tool_names
        assert "create_paper" not in tool_names

    @pytest.mark.asyncio
    async def test_streaming_direct_search_forces_search_after_non_search_tool_roundtrip(self):
        orchestrator = StubStreamingOpenRouterOrchestrator(
            planned_event_sequences=[
                [
                    {"type": "tool_call_detected"},
                    {
                        "type": "result",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "tc-lib-1",
                                "name": "get_project_references",
                                "arguments": {"limit": 20},
                            }
                        ],
                    },
                ],
                [
                    {"type": "token", "content": "Do you want OA-only papers?"},
                    {
                        "type": "result",
                        "content": "Do you want OA-only papers?",
                        "tool_calls": [],
                    },
                ],
            ]
        )
        channel = MockChannel()
        channel.ai_memory = {
            "facts": {
                "research_question": "How does social media usage affect academic performance among university students?",
                "research_topic": "social media and academic performance",
            },
            "research_state": {"stage": "exploring", "stage_history": []},
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

        called_tools = []

        def fake_execute(name, orch, run_ctx, args):
            _ = (orch, run_ctx, args)
            called_tools.append(name)
            if name == "search_papers":
                return {"status": "success", "action": {"type": "search_results", "payload": {}}}
            return {"status": "success", "references": []}

        streamed_events = []
        with patch.object(orchestrator, "update_memory_after_exchange", return_value=None), patch.object(
            orchestrator._tool_registry, "execute", side_effect=fake_execute
        ):
            async for event in orchestrator._execute_with_tools_streaming(messages, ctx):
                streamed_events.append(event)

        result_events = [e for e in streamed_events if e.get("type") == "result"]
        assert result_events, "expected final result event"
        final_data = result_events[-1]["data"]
        assert called_tools == ["get_project_references", "search_papers"]
        assert final_data["message"].startswith("Searching for papers now")
        assert final_data["tools_called"] == ["get_project_references", "search_papers"]

    def test_successful_search_sets_stage_to_finding_papers(self):
        orchestrator = StubToolOrchestrator(
            responses=[
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "name": "search_papers",
                            "arguments": {"query": "sleep deprivation medical residents", "count": 5},
                        }
                    ],
                },
            ]
        )

        channel = MockChannel()
        channel.ai_memory = {
            "facts": {},
            "research_state": {
                "stage": "exploring",
                "stage_confidence": 0.6,
                "stage_history": [],
            },
        }
        ctx = {
            "channel": channel,
            "user_message": "Can you find recent papers on sleep deprivation in medical residents?",
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
        assert channel.ai_memory["research_state"]["stage"] == "finding_papers"
        assert channel.ai_memory["research_state"]["stage_history"][-1]["from"] == "exploring"
        assert channel.ai_memory["research_state"]["stage_history"][-1]["to"] == "finding_papers"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
