"""
Tests for AI Memory System - Phase 1

This test suite verifies the AI memory system functionality:
1. Sliding window (20 messages)
2. Summarization of older messages
3. Research fact extraction
4. Key quote preservation
5. Tool result caching
6. Memory persistence

Run with: pytest tests/test_ai_memory.py -v
Or directly: python tests/test_ai_memory.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest


class MockChannel:
    """Mock ProjectDiscussionChannel for testing."""
    def __init__(self):
        self.id = "test-channel-123"
        self.name = "Test Channel"
        self.ai_memory = None


class MockProject:
    """Mock Project for testing."""
    def __init__(self):
        self.id = "test-project-456"
        self.title = "Test Research Project"
        self.idea = "This is a test project about machine learning."
        self.scope = "Objective 1\nObjective 2"
        self.keywords = "ML, AI, testing"


class MockDB:
    """Mock database session."""
    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def query(self, *args, **kwargs):
        return MockQuery()


class MockQuery:
    """Mock query object."""
    def filter(self, *args, **kwargs):
        return self

    def count(self):
        return 0

    def order_by(self, *args):
        return self

    def limit(self, n):
        return self

    def all(self):
        return []


class MockAIService:
    """Mock AI service for testing."""
    def __init__(self):
        self.default_model = "gpt-4o-mini"
        self.openai_client = MockOpenAIClient()


class MockOpenAIClient:
    """Mock OpenAI client."""
    def __init__(self):
        self.chat = MockChat()


class MockChat:
    """Mock chat completions."""
    def __init__(self):
        self.completions = MockCompletions()


class MockCompletions:
    """Mock completions."""
    def create(self, **kwargs):
        return MockResponse()


class MockResponse:
    """Mock API response."""
    def __init__(self):
        self.choices = [MockChoice()]


class MockChoice:
    """Mock choice."""
    def __init__(self):
        self.message = MockMessage()


class MockMessage:
    """Mock message."""
    def __init__(self):
        self.content = json.dumps({
            "research_topic": "Machine Learning",
            "papers_discussed": [{"title": "Test Paper", "author": "Test Author", "relevance": "test"}],
            "decisions_made": ["Use neural networks"],
            "pending_questions": ["What dataset?"],
            "methodology_notes": ["Deep learning approach"]
        })


# ============================================================
# Test Cases
# ============================================================

class TestAIMemoryBasics:
    """Test basic AI memory operations."""

    def test_get_ai_memory_empty(self):
        """Test getting AI memory when channel has no memory."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = None

        memory = orchestrator._get_ai_memory(channel)

        assert memory is not None
        assert memory.get("summary") is None
        assert "facts" in memory
        assert "key_quotes" in memory
        assert "clarification_state" in memory
        assert memory["facts"]["research_topic"] is None
        assert memory["facts"]["papers_discussed"] == []

        print("✓ test_get_ai_memory_empty passed")

    def test_get_ai_memory_existing(self):
        """Test getting AI memory when channel has existing memory."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "summary": "Previous conversation about ML",
            "facts": {
                "research_topic": "Deep Learning",
                "papers_discussed": [{"title": "Paper 1"}],
                "decisions_made": ["Use PyTorch"],
                "pending_questions": [],
                "methodology_notes": []
            },
            "key_quotes": ["I want to focus on CNNs"],
            "tool_cache": {}
        }

        memory = orchestrator._get_ai_memory(channel)

        assert memory["summary"] == "Previous conversation about ML"
        assert memory["facts"]["research_topic"] == "Deep Learning"
        assert len(memory["facts"]["papers_discussed"]) == 1

        print("✓ test_get_ai_memory_existing passed")

    def test_save_ai_memory(self):
        """Test saving AI memory to channel."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        memory = {
            "summary": "Test summary",
            "facts": {"research_topic": "Testing"},
            "key_quotes": []
        }

        # _save_ai_memory uses its own SessionLocal() for thread safety
        # and flag_modified for JSONB change tracking, so we mock both.
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = channel

        with patch("app.database.SessionLocal", return_value=mock_session), \
             patch("app.services.discussion_ai.mixins.memory_mixin.flag_modified"):
            orchestrator._save_ai_memory(channel, memory)

        assert channel.ai_memory == memory
        mock_session.commit.assert_called_once()

        print("✓ test_save_ai_memory passed")


class TestSlidingWindow:
    """Test sliding window functionality."""

    def test_sliding_window_size_constant(self):
        """Test that SLIDING_WINDOW_SIZE is set to 20."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        assert ToolOrchestrator.SLIDING_WINDOW_SIZE == 20
        print("✓ test_sliding_window_size_constant passed")

    def test_build_messages_with_small_history(self):
        """Test message building with history smaller than window."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        project = MockProject()
        channel = MockChannel()

        # Create 5 messages (less than 20)
        history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(5)
        ]

        messages = orchestrator._build_messages(
            project, channel, "Current message", None, history
        )

        # Should include all 5 history messages
        user_messages = [m for m in messages if m["role"] == "user"]
        # 5 from history + 1 current = 6 user messages
        assert len(user_messages) == 6

        print("✓ test_build_messages_with_small_history passed")

    def test_build_messages_with_large_history(self):
        """Test message building with history larger than window."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        project = MockProject()
        channel = MockChannel()

        # Create 30 messages (more than 20)
        history = [
            {"role": "user", "content": f"Message {i}"}
            for i in range(30)
        ]

        messages = orchestrator._build_messages(
            project, channel, "Current message", None, history
        )

        # Should only include last 20 from history + 1 current
        user_messages = [m for m in messages if m["role"] == "user"]
        assert len(user_messages) == 21  # 20 from window + 1 current

        # Verify it's the LAST 20, not first 20
        # The last message in history is "Message 29"
        history_in_messages = [m["content"] for m in messages if m["role"] == "user" and m["content"] != "Current message"]
        assert "Message 29" in history_in_messages
        assert "Message 0" not in history_in_messages  # First messages should be excluded

        print("✓ test_build_messages_with_large_history passed")


class TestKeyQuoteExtraction:
    """Test key quote extraction functionality."""

    def test_extract_key_quotes_with_patterns(self):
        """Test extracting key quotes from user messages."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        # Test message with "I want" pattern
        message = "I want to focus on neural network architectures for image classification."
        existing_quotes = []

        quotes = orchestrator._extract_key_quotes(message, existing_quotes)

        assert len(quotes) >= 1
        assert any("focus on neural network" in q.lower() for q in quotes)

        print("✓ test_extract_key_quotes_with_patterns passed")

    def test_extract_key_quotes_limit(self):
        """Test that key quotes are limited to 5."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        # Start with 4 existing quotes
        existing_quotes = [f"Quote {i}" for i in range(4)]

        # Add messages that would create more quotes
        message1 = "I want to use transformers. I need better accuracy. I prefer PyTorch."
        quotes = orchestrator._extract_key_quotes(message1, existing_quotes.copy())

        # Should not exceed 5
        assert len(quotes) <= 5

        print("✓ test_extract_key_quotes_limit passed")

    def test_extract_key_quotes_no_duplicates(self):
        """Test that duplicate quotes are not added."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        existing_quotes = ["I want to use neural networks"]
        message = "I want to use neural networks for this project."

        quotes = orchestrator._extract_key_quotes(message, existing_quotes.copy())

        # Should not add duplicate
        assert quotes.count("I want to use neural networks") == 1

        print("✓ test_extract_key_quotes_no_duplicates passed")


class TestToolCaching:
    """Test tool result caching functionality."""

    def test_cache_tool_result(self):
        """Test caching a tool result."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {"tool_cache": {}}

        result = {"count": 5, "references": [{"title": "Paper 1"}]}
        orchestrator.cache_tool_result(channel, "get_project_references", result)

        assert channel.ai_memory["tool_cache"]["get_project_references"]["result"] == result
        assert "timestamp" in channel.ai_memory["tool_cache"]["get_project_references"]

        print("✓ test_cache_tool_result passed")

    def test_get_cached_tool_result_valid(self):
        """Test getting a valid cached result."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        cached_result = {"count": 5, "references": []}
        channel.ai_memory = {
            "tool_cache": {
                "get_project_references": {
                    "result": cached_result,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            }
        }

        result = orchestrator.get_cached_tool_result(channel, "get_project_references")

        assert result == cached_result

        print("✓ test_get_cached_tool_result_valid passed")

    def test_get_cached_tool_result_expired(self):
        """Test that expired cache returns None."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()
        channel.ai_memory = {
            "tool_cache": {
                "get_project_references": {
                    "result": {"count": 5},
                    "timestamp": old_time
                }
            }
        }

        # Default max_age is 300 seconds (5 minutes)
        result = orchestrator.get_cached_tool_result(channel, "get_project_references")

        assert result is None

        print("✓ test_get_cached_tool_result_expired passed")

    def test_get_cached_tool_result_missing(self):
        """Test getting cache for non-existent tool."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {"tool_cache": {}}

        result = orchestrator.get_cached_tool_result(channel, "nonexistent_tool")

        assert result is None

        print("✓ test_get_cached_tool_result_missing passed")


class TestMemoryContext:
    """Test memory context building."""

    def test_build_memory_context_empty(self):
        """Test building memory context with empty memory."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = None

        context = orchestrator._build_memory_context(channel)

        # Empty memory should produce empty context
        assert context == ""

        print("✓ test_build_memory_context_empty passed")

    def test_build_memory_context_with_data(self):
        """Test building memory context with existing data."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "summary": "User is researching transformers for NLP tasks.",
            "facts": {
                "research_topic": "Transformer architectures",
                "papers_discussed": [
                    {"title": "Attention Is All You Need", "author": "Vaswani et al.", "user_reaction": "positive"}
                ],
                "decisions_made": ["Use BERT as baseline"],
                "pending_questions": ["Which dataset to use?"],
                "methodology_notes": []
            },
            "key_quotes": ["I want to focus on encoder-only models"]
        }

        context = orchestrator._build_memory_context(channel)

        assert "Previous Conversation Summary" in context
        assert "researching transformers" in context
        assert "Transformer architectures" in context
        assert "Attention Is All You Need" in context
        assert "Use BERT as baseline" in context
        assert "Which dataset to use?" in context
        assert "I want to focus on encoder-only models" in context

        print("✓ test_build_memory_context_with_data passed")


class TestRequestContext:
    """Test request context building."""

    def test_build_request_context_includes_memory_fields(self):
        """Test that request context includes user_message and conversation_history."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        project = MockProject()
        channel = MockChannel()
        message = "Find papers about transformers"
        history = [{"role": "user", "content": "Hello"}]

        ctx = orchestrator._build_request_context(
            project, channel, message, None, False, history
        )

        assert ctx["user_message"] == message
        assert ctx["conversation_history"] == history
        assert ctx["channel"] == channel
        assert ctx["project"] == project

        print("✓ test_build_request_context_includes_memory_fields passed")


class TestResponseLengthPolicy:
    """Test concise-by-default response length policy injection."""

    def test_build_messages_injects_response_format_guidance(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        project = MockProject()
        channel = MockChannel()

        messages = orchestrator._build_messages(
            project,
            channel,
            "What databases and keywords should we use first for this topic?",
            None,
            [],
            ctx={"user_role": "admin", "current_user": None},
        )
        system_prompt = messages[0]["content"]

        assert "RESPONSE FORMAT" in system_prompt
        assert "Markdown" in system_prompt
        assert "concrete next step" in system_prompt

        print("✓ test_build_messages_injects_response_format_guidance passed")

    def test_apply_response_budget_passes_through_normal_text(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        ctx = {"user_message": "Can you suggest a strategy for this topic?"}
        verbose = ("This is a long explanatory sentence. " * 180).strip()

        result = orchestrator._apply_response_budget(verbose, ctx, [])

        # No truncation — prompt + token cap handle length, not post-processing
        assert result == verbose

    def test_apply_response_budget_uses_short_search_completion(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        ctx = {"user_message": "Can you find me recent papers on this topic?"}
        verbose_search_reply = (
            "I found papers and now I will provide extensive discussion. " * 40
        ).strip()
        tool_results = [{"name": "search_papers", "result": {"status": "success"}}]

        result = orchestrator._apply_response_budget(verbose_search_reply, ctx, tool_results)

        assert result.startswith("Searching for papers now")
        assert len(result.split()) < 40


class TestTokenBudget:
    """Test token budget constants."""

    def test_memory_token_budget_defined(self):
        """Test that memory token budget constants are defined."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        budget = ToolOrchestrator.MEMORY_TOKEN_BUDGET

        assert "working_memory" in budget
        assert "session_summary" in budget
        assert "research_facts" in budget
        assert "key_quotes" in budget

        # Check reasonable values
        assert budget["working_memory"] >= 2000
        assert budget["session_summary"] >= 500
        assert budget["research_facts"] >= 200
        assert budget["key_quotes"] >= 100

        print("✓ test_memory_token_budget_defined passed")


# ============================================================
# Phase 2 Tests
# ============================================================

class TestMemoryPruning:
    """Test memory pruning functionality."""

    def test_prune_stale_cache(self):
        """Test that stale tool cache entries are removed."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator
        from datetime import datetime, timedelta, timezone

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        # Create cache with stale entry (15 minutes old)
        old_time = (datetime.now(timezone.utc) - timedelta(minutes=15)).isoformat()
        channel.ai_memory = {
            "tool_cache": {
                "get_project_references": {
                    "result": {"count": 5},
                    "timestamp": old_time
                }
            },
            "facts": {},
            "key_quotes": []
        }

        orchestrator.prune_stale_memory(channel, cache_max_age_seconds=600)

        # Stale entry should be removed (10 min max age)
        assert "get_project_references" not in channel.ai_memory.get("tool_cache", {})

        print("✓ test_prune_stale_cache passed")

    def test_prune_excess_papers(self):
        """Test that papers list is limited."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        # Create 15 papers
        papers = [{"title": f"Paper {i}", "author": f"Author {i}"} for i in range(15)]
        channel.ai_memory = {
            "facts": {"papers_discussed": papers},
            "tool_cache": {},
            "key_quotes": []
        }

        orchestrator.prune_stale_memory(channel, max_papers=10)

        # Should keep only last 10
        assert len(channel.ai_memory["facts"]["papers_discussed"]) == 10
        # Should keep most recent
        assert channel.ai_memory["facts"]["papers_discussed"][-1]["title"] == "Paper 14"

        print("✓ test_prune_excess_papers passed")

    def test_prune_excess_decisions(self):
        """Test that decisions list is limited."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        decisions = [f"Decision {i}" for i in range(15)]
        channel.ai_memory = {
            "facts": {"decisions_made": decisions},
            "tool_cache": {},
            "key_quotes": []
        }

        orchestrator.prune_stale_memory(channel, max_decisions=10)

        assert len(channel.ai_memory["facts"]["decisions_made"]) == 10
        assert channel.ai_memory["facts"]["decisions_made"][-1] == "Decision 14"

        print("✓ test_prune_excess_decisions passed")


class TestRateLimiting:
    """Test rate limiting for fact extraction."""

    def test_should_update_facts_short_response(self):
        """Test that short responses don't trigger fact extraction."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {"facts": {"research_topic": "NLP"}}

        short_response = "Sure, I can help."
        should_update = orchestrator.should_update_facts(channel, short_response)

        assert should_update is False

        print("✓ test_should_update_facts_short_response passed")

    def test_should_update_facts_no_existing_facts(self):
        """Test that fact extraction triggers when no facts exist."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {"facts": {}}

        long_response = "Here is a detailed analysis " * 50  # >200 chars
        should_update = orchestrator.should_update_facts(channel, long_response)

        # Should update because no facts exist
        assert should_update is True

        print("✓ test_should_update_facts_no_existing_facts passed")

    def test_exchange_counter_increment(self):
        """Test that exchange counter increments properly."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {"_exchanges_since_fact_update": 0}

        orchestrator.increment_exchange_counter(channel)
        assert channel.ai_memory["_exchanges_since_fact_update"] == 1

        orchestrator.increment_exchange_counter(channel)
        assert channel.ai_memory["_exchanges_since_fact_update"] == 2

        print("✓ test_exchange_counter_increment passed")

    def test_exchange_counter_reset(self):
        """Test that exchange counter resets properly."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {"_exchanges_since_fact_update": 5}

        orchestrator.reset_exchange_counter(channel)
        assert channel.ai_memory["_exchanges_since_fact_update"] == 0

        print("✓ test_exchange_counter_reset passed")


class TestContradictionDetection:
    """Test contradiction detection functionality."""

    def test_detect_contradictions_no_facts(self):
        """Test that no contradiction is detected when no facts exist."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        result = orchestrator.detect_contradictions(
            "I want to use BERT.",
            {}  # No existing facts
        )

        # Should return None when no facts to contradict
        assert result is None

        print("✓ test_detect_contradictions_no_facts passed")

    def test_detect_contradictions_method_exists(self):
        """Test that detect_contradictions method exists and is callable."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        assert hasattr(orchestrator, 'detect_contradictions')
        assert callable(orchestrator.detect_contradictions)

        print("✓ test_detect_contradictions_method_exists passed")


class TestUpdateMemoryReturnValue:
    """Test that update_memory_after_exchange returns correctly."""

    def test_update_memory_returns_optional_warning(self):
        """Test that update_memory_after_exchange can return a warning."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator
        import inspect

        # Check the method signature includes Optional return type
        method = ToolOrchestrator.update_memory_after_exchange

        # Check it can be called and returns (at least doesn't raise)
        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {}

        # This should not raise
        result = orchestrator.update_memory_after_exchange(
            channel,
            "Test message",
            "Test response " * 50,  # Make it long enough
            []
        )

        # Result should be None or a string
        assert result is None or isinstance(result, str)

        print("✓ test_update_memory_returns_optional_warning passed")


# ============================================================
# Phase 3 Tests
# ============================================================

class TestResearchStateTracking:
    """Test research state detection and tracking."""

    def test_detect_research_stage_exploring(self):
        """Test detecting exploring stage."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        stage, confidence = orchestrator.detect_research_stage(
            "What should I research for my thesis? I need ideas for a topic.",
            "I can help you explore several research areas...",
            "exploring"
        )

        assert stage == "exploring"
        assert confidence >= 0.5

        print("✓ test_detect_research_stage_exploring passed")

    def test_detect_research_stage_finding_papers(self):
        """Test detecting finding_papers stage."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        stage, confidence = orchestrator.detect_research_stage(
            "Can you find papers about neural network optimization?",
            "I found several recent papers on neural network optimization...",
            "exploring"
        )

        assert stage == "finding_papers"

        print("✓ test_detect_research_stage_finding_papers passed")

    def test_detect_research_stage_writing(self):
        """Test detecting writing stage."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        stage, confidence = orchestrator.detect_research_stage(
            "Help me write the introduction section for my literature review.",
            "Here's a draft introduction for your literature review...",
            "analyzing"
        )

        assert stage == "writing"

        print("✓ test_detect_research_stage_writing passed")

    def test_update_research_state(self):
        """Test updating research state."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "research_state": {
                "stage": "exploring",
                "stage_confidence": 0.5,
                "stage_history": [],
            }
        }

        state = orchestrator.update_research_state(
            channel,
            "Find papers about transformers",
            "Here are some papers about transformers..."
        )

        assert "stage" in state
        assert "stage_confidence" in state
        assert isinstance(state["stage_history"], list)

        print("✓ test_update_research_state passed")


class TestLongTermMemory:
    """Test long-term memory functionality."""

    def test_update_long_term_memory_preferences(self):
        """Test extracting user preferences."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "long_term": {
                "user_preferences": [],
                "rejected_approaches": [],
                "successful_searches": [],
            }
        }

        orchestrator.update_long_term_memory(
            channel,
            "I prefer using recent papers from the last 5 years.",
            "I'll focus on papers from 2021 onwards..."
        )

        prefs = channel.ai_memory["long_term"]["user_preferences"]
        assert len(prefs) >= 1
        assert any("prefer" in p.lower() for p in prefs)

        print("✓ test_update_long_term_memory_preferences passed")

    def test_update_long_term_memory_rejections(self):
        """Test extracting rejected approaches."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "long_term": {
                "user_preferences": [],
                "rejected_approaches": [],
                "successful_searches": [],
            }
        }

        orchestrator.update_long_term_memory(
            channel,
            "I don't want to use traditional machine learning methods.",
            "Understood, I'll focus on deep learning approaches..."
        )

        rejections = channel.ai_memory["long_term"]["rejected_approaches"]
        assert len(rejections) >= 1

        print("✓ test_update_long_term_memory_rejections passed")

    def test_memory_defaults_include_long_term(self):
        """Test that default memory includes long-term structure."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = None

        memory = orchestrator._get_ai_memory(channel)

        assert "long_term" in memory
        assert "user_preferences" in memory["long_term"]
        assert "rejected_approaches" in memory["long_term"]
        assert "follow_up_items" in memory["long_term"]
        assert "user_profiles" in memory["long_term"]

        print("✓ test_memory_defaults_include_long_term passed")

    def test_update_long_term_memory_follow_up_items(self):
        """Explicit deferred questions should be saved as follow-up items."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "long_term": {
                "user_preferences": [],
                "rejected_approaches": [],
                "follow_up_items": [],
            }
        }

        orchestrator.update_long_term_memory(
            channel,
            "I still have an unanswered question for later: What evaluation metrics are most appropriate for measuring bias in large language models?",
            "Short answer: there is no single best metric.",
        )

        follow_ups = channel.ai_memory["long_term"]["follow_up_items"]
        assert len(follow_ups) >= 1
        assert any("evaluation metrics" in item.lower() for item in follow_ups)

        print("✓ test_update_long_term_memory_follow_up_items passed")

    def test_update_long_term_memory_user_scoped_under_channel(self):
        """Preferences/rejections should be isolated per-user under channel memory."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "long_term": {
                "user_preferences": [],
                "rejected_approaches": [],
                "follow_up_items": [],
                "user_profiles": {},
            }
        }

        orchestrator.update_long_term_memory(
            channel,
            "I prefer quantitative methods.",
            "Understood.",
            user_id="user-a",
        )
        orchestrator.update_long_term_memory(
            channel,
            "I don't want survey-only studies.",
            "Understood.",
            user_id="user-b",
        )

        profiles = channel.ai_memory["long_term"]["user_profiles"]
        assert "user-a" in profiles
        assert "user-b" in profiles
        assert any("prefer quantitative" in p.lower() for p in profiles["user-a"]["user_preferences"])
        assert len(profiles["user-a"]["rejected_approaches"]) == 0
        assert any("don't want survey-only" in r.lower() for r in profiles["user-b"]["rejected_approaches"])
        assert len(profiles["user-b"]["user_preferences"]) == 0

        print("✓ test_update_long_term_memory_user_scoped_under_channel passed")


class TestClarificationGuardrails:
    """Test deterministic clarification-loop prevention."""

    def test_scope_clarification_state_tracked(self):
        """Assistant scope clarification should set pending slot state."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {}

        orchestrator._update_clarification_state_inline(
            memory,
            "I want to compare policy interventions used between 2018 and 2025.",
            "Do you want a global comparison or a comparison focused on a specific region/country or up to 6 cities?",
        )

        state = memory.get("clarification_state", {})
        assert state.get("pending_slot") == "scope_geography"
        assert state.get("asked_count") == 1
        assert state.get("default_value") == "global"

        print("✓ test_scope_clarification_state_tracked passed")

    def test_clarification_guardrail_applies_when_user_requests_progress(self):
        """If same slot is still unresolved, next actionable request should force progress."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {
            "clarification_state": {
                "pending_slot": "scope_geography",
                "asked_count": 1,
                "default_value": "global",
                "last_prompt": "Do you want global or specific region?",
            }
        }

        guardrail = orchestrator._build_clarification_guardrail(
            memory,
            "What databases and keywords should we use first for this topic?",
        )

        assert guardrail is not None
        assert "Do NOT ask for geographic scope again" in guardrail
        assert "Assume global scope" in guardrail

        print("✓ test_clarification_guardrail_applies_when_user_requests_progress passed")

    def test_clarification_state_clears_when_user_answers(self):
        """Scope answer from user should clear pending clarification state."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {
            "clarification_state": {
                "pending_slot": "scope_geography",
                "asked_count": 1,
                "default_value": "global",
                "last_prompt": "Do you want global or specific region?",
            }
        }

        orchestrator._update_clarification_state_inline(
            memory,
            "Global comparison is fine.",
            "Understood. I will proceed with global scope.",
        )

        state = memory.get("clarification_state", {})
        assert state.get("pending_slot") is None
        assert state.get("asked_count") == 0

        print("✓ test_clarification_state_clears_when_user_answers passed")

    def test_build_messages_injects_guardrail_instruction(self):
        """System prompt should include clarification guardrail when applicable."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        project = MockProject()
        channel = MockChannel()
        channel.ai_memory = {
            "clarification_state": {
                "pending_slot": "scope_geography",
                "asked_count": 1,
                "default_value": "global",
                "last_prompt": "Do you want global or specific region?",
            },
            "facts": {
                "research_topic": None,
                "research_question": None,
                "papers_discussed": [],
                "decisions_made": [],
                "pending_questions": [],
                "unanswered_questions": [],
                "methodology_notes": [],
            },
            "long_term": {
                "user_preferences": [],
                "rejected_approaches": [],
                "follow_up_items": [],
                "user_profiles": {},
            },
            "research_state": {
                "stage": "refining",
                "stage_confidence": 0.7,
                "stage_history": [],
            },
            "tool_cache": {},
            "key_quotes": [],
        }

        messages = orchestrator._build_messages(
            project,
            channel,
            "What databases and keywords should we use first for this topic?",
            None,
            [],
            ctx={"user_role": "admin", "current_user": None},
        )

        system_prompt = messages[0]["content"]
        assert "CLARIFICATION POLICY" in system_prompt
        assert "Do NOT ask for geographic scope again" in system_prompt

        print("✓ test_build_messages_injects_guardrail_instruction passed")


class TestQuestionTracking:
    """Test unanswered question tracking."""

    def test_track_unanswered_question(self):
        """Test tracking questions AI couldn't answer."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "facts": {
                "unanswered_questions": []
            }
        }

        orchestrator.track_unanswered_question(
            channel,
            "What is the exact implementation of the XYZ algorithm?",
            "I don't have access to the specific implementation details. You might need to check the original paper."
        )

        unanswered = channel.ai_memory["facts"]["unanswered_questions"]
        assert len(unanswered) >= 1

        print("✓ test_track_unanswered_question passed")

    def test_resolve_unanswered_question(self):
        """Test resolving a previously unanswered question."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "facts": {
                "unanswered_questions": ["What is the XYZ algorithm?"]
            }
        }

        orchestrator.resolve_unanswered_question(channel, "XYZ algorithm")

        unanswered = channel.ai_memory["facts"]["unanswered_questions"]
        assert len(unanswered) == 0

        print("✓ test_resolve_unanswered_question passed")

    def test_memory_defaults_include_unanswered_questions(self):
        """Test that default memory includes unanswered questions."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = None

        memory = orchestrator._get_ai_memory(channel)

        assert "unanswered_questions" in memory["facts"]

        print("✓ test_memory_defaults_include_unanswered_questions passed")


class TestDirectRQExtraction:
    """Test direct regex-based research question extraction."""

    def test_extract_rq_explicit_marker(self):
        """Test extracting RQ from explicit 'my research question is:' marker."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        msg = "My research question is: How does social media usage affect academic performance among university students?"
        rq = orchestrator._extract_research_question_direct(msg)

        assert rq is not None
        assert "social media" in rq.lower()
        assert "academic performance" in rq.lower()

        print("✓ test_extract_rq_explicit_marker passed")

    def test_extract_rq_investigation(self):
        """Test extracting RQ from 'I'm investigating...' pattern."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        msg = "I'm investigating the impact of social media on mental health outcomes in teenagers."
        rq = orchestrator._extract_research_question_direct(msg)

        assert rq is not None
        assert "social media" in rq.lower()

        print("✓ test_extract_rq_investigation passed")

    def test_extract_rq_standalone_question(self):
        """Test extracting standalone research question from short message."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        msg = "How does exposure to air pollution during childhood affect long-term cognitive development?"
        rq = orchestrator._extract_research_question_direct(msg)

        assert rq is not None
        assert "air pollution" in rq.lower()

        print("✓ test_extract_rq_standalone_question passed")

    def test_extract_rq_no_match(self):
        """Test that conversational questions don't extract as RQ."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        msg = "Can you help me find papers?"
        rq = orchestrator._extract_research_question_direct(msg)

        assert rq is None

        print("✓ test_extract_rq_no_match passed")

    def test_extract_rq_too_short(self):
        """Test that trivially short questions don't extract."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        msg = "What is X?"
        rq = orchestrator._extract_research_question_direct(msg)

        assert rq is None

        print("✓ test_extract_rq_too_short passed")


class TestShouldUpdateFactsUrgency:
    """Test urgency bypass for should_update_facts rate limiter."""

    def test_urgent_message_bypasses_rate_limit(self):
        """Test that a message with 'research question' triggers even at exchange 0."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "facts": {"research_topic": "NLP"},
            "_exchanges_since_fact_update": 0,
        }

        long_response = "Here is a detailed analysis " * 50
        should_update = orchestrator.should_update_facts(
            channel, long_response, user_message="My research question is about transformers"
        )

        assert should_update is True

        print("✓ test_urgent_message_bypasses_rate_limit passed")

    def test_normal_message_respects_rate_limit(self):
        """Test that 'tell me more' doesn't bypass rate limit."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "facts": {"research_topic": "NLP"},
            "_exchanges_since_fact_update": 0,
        }

        long_response = "Here is a detailed analysis " * 50
        should_update = orchestrator.should_update_facts(
            channel, long_response, user_message="Tell me more about this."
        )

        assert should_update is False

        print("✓ test_normal_message_respects_rate_limit passed")


class TestUnansweredQuestionFixes:
    """Test improved unanswered question tracking (false-positive fixes)."""

    def test_declaration_not_tracked(self):
        """Test that declarative statements aren't tracked as questions."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        memory = {
            "facts": {"unanswered_questions": []},
        }

        # "I know how" is a declaration, not a question
        orchestrator._track_unanswered_question_inline(
            memory,
            "I know how transformers work, right?",
            "Great, let's build on that understanding.",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0

        print("✓ test_declaration_not_tracked passed")

    def test_real_question_tracked(self):
        """Test that a real unanswered question is tracked."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        memory = {
            "facts": {"unanswered_questions": []},
        }

        orchestrator._track_unanswered_question_inline(
            memory,
            "What datasets are commonly used for NER evaluation in biomedical text?",
            "That's a great area to explore, let me think about it.",
        )

        assert len(memory["facts"]["unanswered_questions"]) >= 1

        print("✓ test_real_question_tracked passed")

    def test_short_message_excluded(self):
        """Test that very short messages aren't tracked."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        memory = {
            "facts": {"unanswered_questions": []},
        }

        orchestrator._track_unanswered_question_inline(
            memory,
            "What?",
            "Could you clarify?",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0

        print("✓ test_short_message_excluded passed")

    def test_request_to_ai_not_tracked(self):
        """'Can you find me papers?' is a request, not an unanswered question."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory,
            "Can you find me some recent papers on this topic?",
            "Sure, let me search for those.",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0
        print("✓ test_request_to_ai_not_tracked passed")

    def test_could_you_request_not_tracked(self):
        """'Could you summarize...' is a directive, not a research question."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory,
            "Could you summarize the main findings from these papers?",
            "I'll look into that.",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0
        print("✓ test_could_you_request_not_tracked passed")

    def test_would_you_request_not_tracked(self):
        """'Would you look into...' is a directive."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory,
            "Would you look into the methodology section of that paper?",
            "Let me check that for you.",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0
        print("✓ test_would_you_request_not_tracked passed")

    def test_rq_declaration_not_tracked(self):
        """'My research question is: ...' should not be an unanswered question."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory,
            "My research question is: How does social media usage affect academic performance among university students?",
            "Great question! Let me help you explore that.",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0
        print("✓ test_rq_declaration_not_tracked passed")

    def test_genuine_research_question_still_tracked(self):
        """A real research question with a vague AI response should still be tracked."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory,
            "What evaluation metrics are most appropriate for measuring bias in large language models?",
            "That's an interesting area, I'll need to think about it.",
        )

        assert len(memory["facts"]["unanswered_questions"]) >= 1
        print("✓ test_genuine_research_question_still_tracked passed")

    def test_uppercase_request_not_tracked(self):
        """Uppercase assistant requests should still be excluded."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory,
            "CAN YOU FIND PAPERS ON THIS TOPIC?",
            "Sure, I can help with that.",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0
        print("✓ test_uppercase_request_not_tracked passed")

    def test_whitespace_prefixed_request_not_tracked(self):
        """Leading/trailing whitespace should not affect request filtering."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory,
            "   Do you have recent papers on this method?   ",
            "I can search for those.",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0
        print("✓ test_whitespace_prefixed_request_not_tracked passed")

    def test_is_there_request_not_tracked(self):
        """'Is there ...?' helper request should not be tracked as unresolved."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory,
            "Is there any good benchmark paper for this area?",
            "Yes, I can look that up.",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0
        print("✓ test_is_there_request_not_tracked passed")

    def test_answered_indicator_prevents_tracking(self):
        """Substantive answer indicators should prevent unanswered tracking."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        orchestrator._track_unanswered_question_inline(
            memory,
            "What datasets are best for measuring hallucination in LLMs?",
            "Based on current literature, common datasets include TruthfulQA and HaluEval.",
        )

        assert len(memory["facts"]["unanswered_questions"]) == 0
        print("✓ test_answered_indicator_prevents_tracking passed")

    def test_duplicate_question_not_added_twice(self):
        """The same unresolved question should only be stored once."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        memory = {"facts": {"unanswered_questions": []}}

        message = "What evaluation metrics are most appropriate for measuring bias in large language models?"
        response = "That's an interesting area, I'll need to think about it."

        orchestrator._track_unanswered_question_inline(memory, message, response)
        orchestrator._track_unanswered_question_inline(memory, message, response)

        assert len(memory["facts"]["unanswered_questions"]) == 1
        print("✓ test_duplicate_question_not_added_twice passed")


class TestDirectSearchRouting:
    """Test deterministic direct-search routing helpers."""

    def test_direct_search_request_detected(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        assert orchestrator._is_direct_paper_search_request(
            "Can you find me some recent papers on this topic?"
        ) is True

    def test_library_request_not_detected_as_external_search(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        assert orchestrator._is_direct_paper_search_request(
            "Can you find papers in my library about transformers?"
        ) is False

    def test_fallback_search_query_prefers_memory_topic_for_deictic_requests(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        channel = MockChannel()
        channel.ai_memory = {
            "facts": {
                "research_question": "How does social media usage affect academic performance among university students?",
                "research_topic": "social media and academic performance",
            }
        }
        ctx = {
            "channel": channel,
            "user_message": "Can you find me some recent papers on this topic?",
        }

        query = orchestrator._build_fallback_search_query(ctx)
        assert query.lower() == "social media and academic performance"

    def test_fallback_search_query_strips_request_prefix(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        channel = MockChannel()
        channel.ai_memory = {"facts": {}}
        ctx = {
            "channel": channel,
            "user_message": "Can you find me some recent papers on this topic?",
        }

        query = orchestrator._build_fallback_search_query(ctx)
        assert not query.lower().startswith("can you")
        assert "recent papers on this topic" in query.lower()

    def test_fallback_search_query_preserves_explicit_constraints(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        channel = MockChannel()
        channel.ai_memory = {
            "facts": {
                "research_question": "How does social media usage affect academic performance among university students?",
                "research_topic": "social media and academic performance",
            }
        }
        ctx = {
            "channel": channel,
            "user_message": "Can you find longitudinal papers about social media use and GPA among university students?",
        }

        query = orchestrator._build_fallback_search_query(ctx).lower()
        assert "longitudinal" in query
        assert "gpa" in query
        assert "social media" in query

    def test_user_requested_defaults_detection(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        assert orchestrator._user_requested_open_access("find only open access papers") is True
        assert orchestrator._user_requested_open_access("find papers on this topic") is False
        assert orchestrator._user_requested_count("find 12 papers on this topic") is True
        assert orchestrator._user_requested_count("find papers on this topic") is False

    def test_execute_tool_calls_applies_direct_search_guardrail(self):
        from unittest.mock import patch
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        channel = MockChannel()
        channel.ai_memory = {
            "facts": {
                "research_question": "How does social media usage affect academic performance among university students?",
                "research_topic": "social media and academic performance",
            }
        }

        ctx = {
            "user_message": "Can you find me some recent papers on this topic?",
            "channel": channel,
            "user_role": "admin",
            "is_owner": True,
        }
        tool_calls = [{
            "id": "tc-1",
            "name": "search_papers",
            "arguments": {
                "query": "social media use academic performance university students longitudinal GPA recent",
                "count": 10,
                "open_access_only": True,
            },
        }]

        captured_args = {}

        def fake_execute(name, orch, run_ctx, args):
            captured_args.update(args)
            return {"status": "ok"}

        with patch.object(orchestrator._tool_registry, "execute", side_effect=fake_execute):
            results = orchestrator._execute_tool_calls(tool_calls, ctx)

        assert results[0]["name"] == "search_papers"
        assert captured_args["query"] == "social media and academic performance"
        assert captured_args["count"] == 5
        assert captured_args["limit"] == 5
        assert captured_args["open_access_only"] is False
        assert captured_args["year_from"] is not None
        assert captured_args["year_to"] is not None

    def test_execute_tool_calls_honors_user_requested_count_and_oa(self):
        from unittest.mock import patch
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        channel = MockChannel()
        channel.ai_memory = {
            "facts": {
                "research_topic": "sleep deprivation and cognitive function in medical residents",
            }
        }

        ctx = {
            "user_message": "Can you find 12 open access papers on this topic?",
            "channel": channel,
            "user_role": "admin",
            "is_owner": True,
        }
        tool_calls = [{
            "id": "tc-2",
            "name": "search_papers",
            "arguments": {
                "query": "some noisy query",
                "count": 2,
                "open_access_only": False,
            },
        }]

        captured_args = {}

        def fake_execute(name, orch, run_ctx, args):
            captured_args.update(args)
            return {"status": "ok"}

        with patch.object(orchestrator._tool_registry, "execute", side_effect=fake_execute):
            results = orchestrator._execute_tool_calls(tool_calls, ctx)

        assert results[0]["name"] == "search_papers"
        assert captured_args["count"] == 12
        assert captured_args["limit"] == 12
        assert captured_args["open_access_only"] is True
        assert "sleep deprivation" in captured_args["query"].lower()

    def test_execute_tool_calls_honors_explicit_year_range(self):
        from unittest.mock import patch
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        orchestrator = ToolOrchestrator(MockAIService(), MockDB())
        channel = MockChannel()
        channel.ai_memory = {
            "facts": {
                "research_topic": "social media and academic performance",
            }
        }

        ctx = {
            "user_message": "Can you find papers from 2020 to 2023 on this topic?",
            "channel": channel,
            "user_role": "admin",
            "is_owner": True,
        }
        tool_calls = [{
            "id": "tc-3",
            "name": "search_papers",
            "arguments": {
                "query": "noisy query",
                "count": 2,
                "open_access_only": False,
            },
        }]

        captured_args = {}

        def fake_execute(name, orch, run_ctx, args):
            captured_args.update(args)
            return {"status": "ok"}

        with patch.object(orchestrator._tool_registry, "execute", side_effect=fake_execute):
            results = orchestrator._execute_tool_calls(tool_calls, ctx)

        assert results[0]["name"] == "search_papers"
        assert captured_args["year_from"] == 2020
        assert captured_args["year_to"] == 2023


class TestIncrementalSummary:
    """Test incremental summary generation for short sessions."""

    def test_summary_generated_at_6_messages(self):
        """Test that summary is generated when >= 6 messages and no existing summary."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator
        from unittest.mock import patch, MagicMock

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {}

        # Build 6 messages of conversation history
        conversation_history = [
            {"role": "user", "content": f"Message {i} about research topic with enough detail"}
            for i in range(6)
        ]

        # Mock the summarization and save methods
        with patch.object(orchestrator, '_summarize_old_messages', return_value="Test summary") as mock_summarize, \
             patch.object(orchestrator, '_save_ai_memory') as mock_save, \
             patch('app.services.discussion_ai.token_utils.should_summarize', return_value=False):
            orchestrator.update_memory_after_exchange(
                channel,
                "Latest user message about the research",
                "Here is a detailed response about the research topic. " * 50,
                conversation_history,
            )

        # Verify summarization was called
        mock_summarize.assert_called_once()

        print("✓ test_summary_generated_at_6_messages passed")


class TestSessionReturn:
    """Test welcome-back context generation."""

    def test_get_session_context_for_return(self):
        """Test generating context for returning user."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        db = MockDB()
        ai_service = MockAIService()
        orchestrator = ToolOrchestrator(ai_service, db)

        channel = MockChannel()
        channel.ai_memory = {
            "research_state": {
                "stage": "finding_papers",
                "stage_confidence": 0.8,
                "stage_history": [],
            },
            "facts": {
                "research_topic": "Neural network optimization",
                "decisions_made": ["Focus on Adam optimizer variants"],
                "pending_questions": ["Which learning rate schedule?"],
                "unanswered_questions": [],
                "papers_discussed": [],
                "methodology_notes": [],
            },
            "long_term": {
                "user_preferences": ["I prefer recent papers"],
                "rejected_approaches": [],
                "successful_searches": [],
            },
            "key_quotes": [],
        }

        context = orchestrator.get_session_context_for_return(channel)

        assert "Welcome Back" in context
        assert "finding_papers" in context.lower() or "searching" in context.lower()
        assert "Neural network optimization" in context
        assert "Adam optimizer" in context

        print("✓ test_get_session_context_for_return passed")


class TestResearchStages:
    """Test research stage constants."""

    def test_research_stages_defined(self):
        """Test that research stages are defined."""
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        stages = ToolOrchestrator.RESEARCH_STAGES

        assert "exploring" in stages
        assert "refining" in stages
        assert "finding_papers" in stages
        assert "analyzing" in stages
        assert "writing" in stages

        print("✓ test_research_stages_defined passed")


# ============================================================
# Run Tests
# ============================================================

def run_all_tests():
    """Run all tests and report results."""
    print("\n" + "=" * 60)
    print("AI Memory System - Phase 1, 2 & 3 Tests")
    print("=" * 60 + "\n")

    test_classes = [
        # Phase 1
        TestAIMemoryBasics,
        TestSlidingWindow,
        TestKeyQuoteExtraction,
        TestToolCaching,
        TestMemoryContext,
        TestRequestContext,
        TestTokenBudget,
        # Phase 2
        TestMemoryPruning,
        TestRateLimiting,
        TestContradictionDetection,
        TestUpdateMemoryReturnValue,
        # Phase 3
        TestResearchStateTracking,
        TestLongTermMemory,
        TestQuestionTracking,
        TestSessionReturn,
        TestResearchStages,
        # Memory reliability fixes
        TestDirectRQExtraction,
        TestShouldUpdateFactsUrgency,
        TestUnansweredQuestionFixes,
        TestIncrementalSummary,
    ]

    passed = 0
    failed = 0
    errors = []

    for test_class in test_classes:
        print(f"\n--- {test_class.__name__} ---")
        instance = test_class()

        for method_name in dir(instance):
            if method_name.startswith("test_"):
                try:
                    method = getattr(instance, method_name)
                    method()
                    passed += 1
                except AssertionError as e:
                    failed += 1
                    errors.append((test_class.__name__, method_name, str(e)))
                    print(f"✗ {method_name} FAILED: {e}")
                except Exception as e:
                    failed += 1
                    errors.append((test_class.__name__, method_name, str(e)))
                    print(f"✗ {method_name} ERROR: {e}")

    print("\n" + "=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    if errors:
        print("\nFailed tests:")
        for cls, method, error in errors:
            print(f"  - {cls}.{method}: {error}")

    return failed == 0


if __name__ == "__main__":
    # Change to backend directory for imports
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(backend_dir)

    success = run_all_tests()
    sys.exit(0 if success else 1)
