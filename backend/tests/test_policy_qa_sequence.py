"""
Automated tests that simulate the 6-step manual QA sequence from MANUAL_QA_MEMORY.md.

Validates the DiscussionPolicy layer deterministically without needing the
actual AI model or database.  Every assertion corresponds to a specific row
in the manual QA checklist.

Run with: pytest tests/test_policy_qa_sequence.py -v
"""

import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.services.discussion_ai.policy import DiscussionPolicy


CURRENT_YEAR = datetime.now(timezone.utc).year


# ---------------------------------------------------------------------------
# TestManualQASequence -- simulates the 6-step QA flow with carry-over state
# ---------------------------------------------------------------------------

class TestManualQASequence:
    """Simulate the six-step manual QA sequence end-to-end.

    Each step feeds the same DiscussionPolicy instance (stateless -- but we
    pass carry-over state explicitly via topic_hint / last_search_topic
    exactly as the orchestrator would).
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.policy = DiscussionPolicy()

    # -- Step 1 --
    # "My research question is: How does sleep deprivation affect cognitive
    #  function in medical residents?"
    # This is a *statement*, not a search request.

    def test_step1_not_direct_search(self):
        msg = (
            "My research question is: How does sleep deprivation affect "
            "cognitive function in medical residents?"
        )
        assert self.policy.is_direct_paper_search_request(msg) is False

    def test_step1_general_intent(self):
        msg = (
            "My research question is: How does sleep deprivation affect "
            "cognitive function in medical residents?"
        )
        decision = self.policy.build_decision(msg)
        assert decision.intent == "general"

    # -- Step 2 --
    # "Can you find me 5 recent papers on this topic?"
    # Deictic -- falls back to topic_hint (simulating memory).

    def test_step2_is_direct_search(self):
        msg = "Can you find me 5 recent papers on this topic?"
        assert self.policy.is_direct_paper_search_request(msg) is True

    def test_step2_decision(self):
        msg = "Can you find me 5 recent papers on this topic?"
        topic_hint = (
            "How does sleep deprivation affect cognitive function "
            "in medical residents"
        )
        decision = self.policy.build_decision(
            msg, topic_hint=topic_hint,
        )
        assert decision.intent == "direct_search"
        assert decision.search is not None
        assert decision.search.count == 5
        # The query should reflect the actual topic, not filler like
        # "5 recent papers on this topic".
        assert "sleep" in decision.search.query.lower()
        assert decision.search.year_from == CURRENT_YEAR - 4
        assert decision.search.year_to == CURRENT_YEAR

    # -- Step 3 --
    # "Can you find another 3 papers?"
    # Relative-only -- falls back to last_search_topic.

    def test_step3_is_direct_search(self):
        msg = "Can you find another 3 papers?"
        assert self.policy.is_direct_paper_search_request(msg) is True

    def test_step3_decision(self):
        msg = "Can you find another 3 papers?"
        last_topic = "sleep deprivation cognitive function medical residents"
        decision = self.policy.build_decision(
            msg, last_search_topic=last_topic,
        )
        assert decision.intent == "direct_search"
        assert decision.search is not None
        assert decision.search.count == 3
        # Must NOT be the literal filler text.
        assert decision.search.query.lower() != "another 3 papers"
        # Must carry over the actual topic.
        assert "sleep" in decision.search.query.lower()

    # -- Step 4 --
    # "Find 4 open access papers from the last 3 years on this topic."
    # Deictic + open-access + year range.

    def test_step4_is_direct_search(self):
        msg = "Find 4 open access papers from the last 3 years on this topic."
        assert self.policy.is_direct_paper_search_request(msg) is True

    def test_step4_decision(self):
        msg = "Find 4 open access papers from the last 3 years on this topic."
        last_topic = "sleep deprivation cognitive function medical residents"
        decision = self.policy.build_decision(
            msg, last_search_topic=last_topic,
        )
        assert decision.intent == "direct_search"
        assert decision.search is not None
        assert decision.search.count == 4
        assert decision.search.open_access_only is True
        # "last 3 years" => current_year - 3 + 1 = current_year - 2
        assert decision.search.year_from == CURRENT_YEAR - 2
        assert decision.search.year_to == CURRENT_YEAR
        # Topic should resolve from fallback, not be the cleaned filler.
        assert "sleep" in decision.search.query.lower()

    # -- Step 5 --
    # "Please update project keywords to sleep deprivation, cognition,
    #  medical residents."

    def test_step5_is_project_update(self):
        msg = (
            "Please update project keywords to sleep deprivation, "
            "cognition, medical residents."
        )
        assert self.policy.is_project_update_request(msg) is True

    def test_step5_decision(self):
        msg = (
            "Please update project keywords to sleep deprivation, "
            "cognition, medical residents."
        )
        decision = self.policy.build_decision(msg)
        assert decision.intent == "project_update"
        assert decision.action_plan is not None
        assert decision.action_plan.primary_tool == "update_project_info"
        # Search tools must be blocked during a project-update turn.
        blocked = set(decision.action_plan.blocked_tools)
        assert "search_papers" in blocked
        assert "batch_search_papers" in blocked
        assert "discover_topics" in blocked

    # -- Step 6 --
    # "Can you find papers on climate adaptation policy from 2021 to 2024?"
    # Explicit topic + explicit year range.

    def test_step6_is_direct_search(self):
        msg = "Can you find papers on climate adaptation policy from 2021 to 2024?"
        assert self.policy.is_direct_paper_search_request(msg) is True

    def test_step6_decision(self):
        msg = "Can you find papers on climate adaptation policy from 2021 to 2024?"
        decision = self.policy.build_decision(msg)
        assert decision.intent == "direct_search"
        assert decision.search is not None
        # Explicit topic -- must contain "climate adaptation policy".
        assert "climate adaptation policy" in decision.search.query.lower()
        assert decision.search.year_from == 2021
        assert decision.search.year_to == 2024


# ---------------------------------------------------------------------------
# TestPolicyHelpers -- standalone unit tests for extraction helpers
# ---------------------------------------------------------------------------

class TestPolicyHelpers:
    """Unit tests for individual extraction / detection helpers."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.policy = DiscussionPolicy()

    # -- extract_requested_paper_count --

    def test_extract_count_5_recent_papers(self):
        count = self.policy.extract_requested_paper_count(
            "find me 5 recent papers"
        )
        assert count == 5

    def test_extract_count_another_3(self):
        count = self.policy.extract_requested_paper_count(
            "find another 3 papers"
        )
        assert count == 3

    def test_extract_count_4_open_access(self):
        count = self.policy.extract_requested_paper_count(
            "find 4 open access papers"
        )
        assert count == 4

    # -- user_requested_open_access --

    def test_open_access_detection(self):
        assert self.policy.user_requested_open_access(
            "find open access papers on neural networks"
        ) is True

    def test_open_access_negative(self):
        assert self.policy.user_requested_open_access(
            "find papers on neural networks"
        ) is False

    # -- extract_year_bounds --

    def test_year_range_from_to(self):
        year_from, year_to = self.policy.extract_year_bounds(
            "find papers from 2021 to 2024"
        )
        assert year_from == 2021
        assert year_to == 2024

    def test_year_recent(self):
        year_from, year_to = self.policy.extract_year_bounds(
            "find recent papers on AI"
        )
        assert year_from == CURRENT_YEAR - 4
        assert year_to == CURRENT_YEAR

    def test_year_last_3_years(self):
        year_from, year_to = self.policy.extract_year_bounds(
            "papers from the last 3 years"
        )
        assert year_from == CURRENT_YEAR - 2
        assert year_to == CURRENT_YEAR

    # -- _RELATIVE_ONLY_RE --

    def test_relative_only_detection(self):
        pattern = DiscussionPolicy._RELATIVE_ONLY_RE
        assert pattern.match("another 3 papers") is not None

    def test_relative_only_more_papers(self):
        pattern = DiscussionPolicy._RELATIVE_ONLY_RE
        assert pattern.match("more papers") is not None

    def test_relative_only_negative(self):
        pattern = DiscussionPolicy._RELATIVE_ONLY_RE
        # An explicit topic should NOT match.
        assert pattern.match("climate adaptation policy papers") is None

    # -- deictic detection --

    def test_deictic_detection(self):
        markers = DiscussionPolicy._DEICTIC_MARKERS
        text = "5 recent papers on this topic"
        assert any(marker in text.lower() for marker in markers)

    def test_deictic_negative(self):
        markers = DiscussionPolicy._DEICTIC_MARKERS
        text = "papers on climate adaptation policy"
        assert not any(marker in text.lower() for marker in markers)

    # -- _infer_update_mode_from_message (lives in ToolOrchestrator) --

    def test_infer_update_mode_add(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mode = ToolOrchestrator._infer_update_mode_from_message(
            "add keywords sleep, cognition"
        )
        assert mode == "append"

    def test_infer_update_mode_replace(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mode = ToolOrchestrator._infer_update_mode_from_message(
            "update keywords to sleep deprivation, cognition"
        )
        assert mode == "replace"

    def test_infer_update_mode_remove(self):
        from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator

        mode = ToolOrchestrator._infer_update_mode_from_message(
            "remove keyword cognition"
        )
        assert mode == "remove"


# ---------------------------------------------------------------------------
# TestContextResolution -- resolve_search_context() directly
# ---------------------------------------------------------------------------

class TestContextResolution:
    """Test the deterministic context-resolution logic in isolation."""

    @pytest.fixture(autouse=True)
    def _setup(self):
        self.policy = DiscussionPolicy()

    def test_explicit_topic(self):
        """An explicit topic in the user message takes priority."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers on climate adaptation policy from 2021 to 2024?",
        )
        assert resolution.source == "explicit_user_topic"
        assert "climate adaptation policy" in resolution.resolved_topic.lower()
        assert resolution.is_deictic is False
        assert resolution.is_relative_only is False

    def test_deictic_with_topic_hint(self):
        """Deictic reference ('on this topic') resolves via topic_hint."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find me 5 recent papers on this topic?",
            topic_hint="sleep deprivation cognitive function medical residents",
        )
        assert resolution.source == "memory_topic_hint"
        assert "sleep" in resolution.resolved_topic.lower()
        assert resolution.is_deictic is True
        assert resolution.is_relative_only is False

    def test_relative_only_with_last_search_topic(self):
        """Relative-only request ('another 3 papers') resolves via last_search_topic."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find another 3 papers?",
            last_search_topic="sleep deprivation cognitive function medical residents",
        )
        assert resolution.source == "last_search_topic"
        assert "sleep" in resolution.resolved_topic.lower()
        assert resolution.is_relative_only is True

    def test_no_context_fallback(self):
        """When there is no context at all, the source should be fallback_default."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find another 3 papers?",
        )
        assert resolution.source == "fallback_default"

    def test_deictic_without_hint_falls_to_last_search(self):
        """Deictic without topic_hint should fall back to last_search_topic."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find me 5 recent papers on this topic?",
            last_search_topic="neuroscience memory consolidation",
        )
        assert resolution.source == "last_search_topic"
        assert "neuroscience" in resolution.resolved_topic.lower()

    def test_deictic_without_any_context(self):
        """Deictic with no topic_hint and no last_search_topic => fallback."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find me 5 recent papers on this topic?",
        )
        assert resolution.source == "fallback_default"

    def test_explicit_topic_overrides_hints(self):
        """An explicit topic takes precedence even if hints are present."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers on machine learning fairness?",
            topic_hint="sleep deprivation cognitive function",
            last_search_topic="climate adaptation policy",
        )
        assert resolution.source == "explicit_user_topic"
        assert "machine learning fairness" in resolution.resolved_topic.lower()

    def test_low_info_my_project_falls_through(self):
        """'about my project' is low-info — should fall through to topic_hint."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers about my project?",
            topic_hint="AI-powered drug discovery",
        )
        assert resolution.source == "memory_topic_hint"
        assert "drug discovery" in resolution.resolved_topic.lower()

    def test_low_info_my_project_falls_to_project_context(self):
        """'about my project' with no memory falls through to project_context."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers about my project?",
            project_context="AI-Powered Drug Discovery",
        )
        assert resolution.source == "project_context"
        assert "drug discovery" in resolution.resolved_topic.lower()

    def test_low_info_my_research_falls_through(self):
        """'about my research' is low-info — should fall through."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers about my research?",
            last_search_topic="transformer architectures",
        )
        assert resolution.source == "last_search_topic"
        assert "transformer" in resolution.resolved_topic.lower()

    def test_low_info_this_project_falls_through(self):
        """'about this project' is low-info — should fall through."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers about this project?",
            project_context="sleep deprivation, cognition, medical residents",
        )
        assert resolution.source == "project_context"

    def test_substantive_topic_not_low_info(self):
        """'climate adaptation policy' has substance — should stay explicit."""
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers on climate adaptation policy?",
            topic_hint="something else entirely",
        )
        assert resolution.source == "explicit_user_topic"
        assert "climate adaptation policy" in resolution.resolved_topic.lower()

    def test_project_context_priority_order(self):
        """project_context is used only when memory and last_search are empty."""
        # With topic_hint → memory wins
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers about my project?",
            topic_hint="neural networks",
            project_context="drug discovery",
        )
        assert resolution.source == "memory_topic_hint"

        # Without topic_hint but with last_search → last_search wins
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers about my project?",
            last_search_topic="deep learning",
            project_context="drug discovery",
        )
        assert resolution.source == "last_search_topic"

        # Without both → project_context wins over fallback
        resolution = self.policy.resolve_search_context(
            user_message="Can you find papers about my project?",
            project_context="drug discovery",
        )
        assert resolution.source == "project_context"


# ---------------------------------------------------------------------------
# TestLowInformationQuery -- is_low_information_query() tests
# ---------------------------------------------------------------------------

class TestLowInformationQuery:
    """Tests for the low-information query detector."""

    @pytest.mark.parametrize("query", [
        "papers about my project",
        "my project",
        "this research",
        "our project",
        "about it",
        "more papers",
        "some recent papers",
        "the topic",
        "3 papers about my project",
        "find me papers about this",
        "",
    ])
    def test_low_info_detected(self, query):
        assert DiscussionPolicy.is_low_information_query(query) is True

    @pytest.mark.parametrize("query", [
        "climate adaptation policy",
        "transformer architectures for NLP",
        "sleep deprivation cognitive function medical residents",
        "machine learning fairness",
        "BERT pre-training",
        "drug discovery",
        "convolutional neural networks",
    ])
    def test_substantive_query_not_low_info(self, query):
        assert DiscussionPolicy.is_low_information_query(query) is False
