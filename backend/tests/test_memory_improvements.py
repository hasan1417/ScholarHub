"""Tests for memory system improvements (Section 8.4).

Tests:
1. research_question field in default schema and migration guard
2. focused_papers cap at 20
3. Removal of dead successful_searches field
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from app.services.discussion_ai.mixins.memory_mixin import MemoryMixin


class FakeChannel:
    """Minimal channel stub for testing."""

    def __init__(self, ai_memory=None):
        self.id = "test-channel-1"
        self.ai_memory = ai_memory


class ConcreteMemoryMixin(MemoryMixin):
    """Concrete class to test the mixin in isolation."""

    def __init__(self):
        self.ai_service = MagicMock()
        self.ai_service.openai_client = None  # Disable LLM calls
        self.db = MagicMock()
        self._model = "gpt-4o-mini"

    @property
    def model(self) -> str:
        return self._model


# ---------------------------------------------------------------------------
# Change 1: research_question field
# ---------------------------------------------------------------------------

class TestResearchQuestionField:
    def test_research_question_in_default_schema(self):
        """research_question key exists in freshly-initialized memory."""
        mixin = ConcreteMemoryMixin()
        channel = FakeChannel(ai_memory=None)
        memory = mixin._get_ai_memory(channel)

        assert "research_question" in memory["facts"]
        assert memory["facts"]["research_question"] is None
        assert "follow_up_items" in memory["long_term"]
        assert memory["long_term"]["follow_up_items"] == []
        assert "user_profiles" in memory["long_term"]
        assert memory["long_term"]["user_profiles"] == {}

    def test_research_question_migration_guard(self):
        """Old memory without research_question gets it added."""
        old_memory = {
            "summary": None,
            "facts": {
                "research_topic": "NLP",
                "papers_discussed": [],
                "decisions_made": [],
                "pending_questions": [],
                "unanswered_questions": [],
                "methodology_notes": [],
                # NOTE: no research_question key
            },
            "research_state": {
                "stage": "exploring",
                "stage_confidence": 0.5,
                "stage_history": [],
            },
            "long_term": {
                "user_preferences": [],
                "rejected_approaches": [],
            },
            "key_quotes": [],
            "last_summarized_exchange_id": None,
            "tool_cache": {},
        }
        mixin = ConcreteMemoryMixin()
        channel = FakeChannel(ai_memory=old_memory)
        memory = mixin._get_ai_memory(channel)

        assert memory["facts"]["research_question"] is None
        assert memory["long_term"]["follow_up_items"] == []
        assert memory["long_term"]["user_profiles"] == {}

    def test_research_question_in_extraction_prompt(self):
        """The fact extraction prompt asks for research_question."""
        mixin = ConcreteMemoryMixin()
        # We can't easily call _extract_research_facts without an LLM,
        # but we can verify the prompt text by inspecting the source.
        import inspect
        source = inspect.getsource(mixin._extract_research_facts)
        assert "research_question" in source

    def test_research_question_in_context_display(self):
        """research_question appears in built context when set."""
        mixin = ConcreteMemoryMixin()
        memory = {
            "summary": None,
            "facts": {
                "research_topic": "Machine Learning",
                "research_question": "How does transfer learning affect NER in low-resource languages?",
                "papers_discussed": [],
                "decisions_made": [],
                "pending_questions": [],
                "unanswered_questions": [],
                "methodology_notes": [],
            },
            "research_state": {"stage": "exploring", "stage_confidence": 0.5, "stage_history": []},
            "long_term": {"user_preferences": [], "rejected_approaches": []},
            "key_quotes": [],
            "tool_cache": {},
        }

        context = mixin._build_memory_context_core(memory)
        assert "Research Question:" in context
        assert "transfer learning" in context

    def test_research_question_not_shown_when_none(self):
        """research_question line is omitted when None."""
        mixin = ConcreteMemoryMixin()
        memory = {
            "summary": None,
            "facts": {
                "research_topic": "ML",
                "research_question": None,
                "papers_discussed": [],
                "decisions_made": [],
                "pending_questions": [],
                "unanswered_questions": [],
                "methodology_notes": [],
            },
            "research_state": {"stage": "exploring", "stage_confidence": 0.5, "stage_history": []},
            "long_term": {"user_preferences": [], "rejected_approaches": []},
            "key_quotes": [],
            "tool_cache": {},
        }

        context = mixin._build_memory_context_core(memory)
        assert "Research Question:" not in context


# ---------------------------------------------------------------------------
# Change 2: focused_papers cap at 20
# ---------------------------------------------------------------------------

class TestFocusedPapersCap:
    def test_focused_papers_cap_in_pruning(self):
        """25 focused papers are pruned to 20 by _prune_stale_memory_inline."""
        mixin = ConcreteMemoryMixin()
        papers = [{"title": f"Paper {i}", "year": 2024} for i in range(25)]
        memory = {
            "facts": {
                "papers_discussed": [],
                "decisions_made": [],
                "methodology_notes": [],
            },
            "tool_cache": {},
            "focused_papers": papers,
        }

        mixin._prune_stale_memory_inline(memory)

        assert len(memory["focused_papers"]) == 20
        # Should keep the LAST 20 (most recent)
        assert memory["focused_papers"][0]["title"] == "Paper 5"
        assert memory["focused_papers"][-1]["title"] == "Paper 24"

    def test_focused_papers_under_cap_not_pruned(self):
        """Papers under the cap are left untouched."""
        mixin = ConcreteMemoryMixin()
        papers = [{"title": f"Paper {i}", "year": 2024} for i in range(10)]
        memory = {
            "facts": {
                "papers_discussed": [],
                "decisions_made": [],
                "methodology_notes": [],
            },
            "tool_cache": {},
            "focused_papers": papers,
        }

        mixin._prune_stale_memory_inline(memory)
        assert len(memory["focused_papers"]) == 10

    def test_focused_papers_cap_at_save(self):
        """_tool_focus_on_papers caps at 20 when saving."""
        from app.services.discussion_ai.mixins.analysis_tools_mixin import AnalysisToolsMixin

        # Verify the cap is in the source code of _tool_focus_on_papers
        import inspect
        source = inspect.getsource(AnalysisToolsMixin._tool_focus_on_papers)
        assert "[-20:]" in source


# ---------------------------------------------------------------------------
# Change 3: dead successful_searches removed
# ---------------------------------------------------------------------------

class TestDeadFieldsRemoved:
    def test_successful_searches_removed_from_default_schema(self):
        """successful_searches is no longer in freshly-initialized memory."""
        mixin = ConcreteMemoryMixin()
        channel = FakeChannel(ai_memory=None)
        memory = mixin._get_ai_memory(channel)

        assert "successful_searches" not in memory.get("long_term", {})

    def test_long_term_memory_no_dead_fields(self):
        """Inline updater fallback dict has no dead fields."""
        import inspect
        source = inspect.getsource(MemoryMixin._update_long_term_memory_inline)
        assert "successful_strategies" not in source
        assert "successful_searches" not in source

    def test_legacy_updater_no_dead_fields(self):
        """Legacy update_long_term_memory fallback dict has no dead fields."""
        import inspect
        source = inspect.getsource(MemoryMixin.update_long_term_memory)
        assert "successful_searches" not in source
