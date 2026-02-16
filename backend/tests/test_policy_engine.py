"""Unit tests for the deterministic policy engine.

Tests pure functions in DiscussionPolicy: year extraction, paper count
extraction, low-information detection, search context resolution,
intent classification, deictic markers, open access detection, and
detailed-response detection.

Run:
    python -m pytest tests/test_policy_engine.py -v
"""

import pytest
from datetime import datetime, timezone

from app.services.discussion_ai.policy import DiscussionPolicy


@pytest.fixture
def policy():
    return DiscussionPolicy()


CURRENT_YEAR = datetime.now(timezone.utc).year


# ── extract_year_bounds ─────────────────────────────────────────────────


class TestExtractYearBounds:
    """Test DiscussionPolicy.extract_year_bounds static method."""

    def test_last_n_years(self, policy):
        year_from, year_to = policy.extract_year_bounds("find papers from the last 3 years")
        assert year_from == CURRENT_YEAR - 2
        assert year_to == CURRENT_YEAR

    def test_past_n_years(self, policy):
        year_from, year_to = policy.extract_year_bounds("past 5 years research")
        assert year_from == CURRENT_YEAR - 4
        assert year_to == CURRENT_YEAR

    def test_since_year(self, policy):
        year_from, year_to = policy.extract_year_bounds("papers since 2020")
        assert year_from == 2020
        assert year_to == CURRENT_YEAR

    def test_from_year_to_year(self, policy):
        year_from, year_to = policy.extract_year_bounds("from 2018 to 2022")
        assert year_from == 2018
        assert year_to == 2022

    def test_between_year_and_year(self, policy):
        year_from, year_to = policy.extract_year_bounds("between 2019 and 2023")
        assert year_from == 2019
        assert year_to == 2023

    def test_dash_range(self, policy):
        year_from, year_to = policy.extract_year_bounds("papers 2015-2020")
        assert year_from == 2015
        assert year_to == 2020

    def test_recent_papers_generic(self, policy):
        year_from, year_to = policy.extract_year_bounds("recent papers on NLP")
        assert year_from == CURRENT_YEAR - 4
        assert year_to == CURRENT_YEAR

    def test_latest_keyword(self, policy):
        year_from, year_to = policy.extract_year_bounds("latest studies on transformers")
        assert year_from == CURRENT_YEAR - 4
        assert year_to == CURRENT_YEAR

    def test_single_year_with_temporal_signal(self, policy):
        year_from, year_to = policy.extract_year_bounds("papers published in 2024")
        assert year_from == 2024
        assert year_to == 2024

    def test_single_year_without_temporal_signal_returns_none(self, policy):
        """A bare year mention without 'in/during/around/published' should not trigger."""
        year_from, year_to = policy.extract_year_bounds("2024 papers on AI")
        assert year_from is None
        assert year_to is None

    def test_empty_input(self, policy):
        assert policy.extract_year_bounds("") == (None, None)

    def test_none_input(self, policy):
        assert policy.extract_year_bounds(None) == (None, None)

    def test_no_year_info(self, policy):
        assert policy.extract_year_bounds("find papers on machine learning") == (None, None)

    def test_inverted_range_swapped(self, policy):
        """If the user writes years in reverse order, they should be swapped."""
        year_from, year_to = policy.extract_year_bounds("from 2023 to 2019")
        assert year_from == 2019
        assert year_to == 2023

    def test_last_1_year(self, policy):
        year_from, year_to = policy.extract_year_bounds("last 1 year of research")
        assert year_from == CURRENT_YEAR
        assert year_to == CURRENT_YEAR


# ── extract_requested_paper_count ────────────────────────────────────────


class TestExtractRequestedPaperCount:
    """Test DiscussionPolicy.extract_requested_paper_count static method."""

    def test_digit_count(self, policy):
        assert policy.extract_requested_paper_count("find 5 papers on AI") == 5

    def test_word_count_ten(self, policy):
        assert policy.extract_requested_paper_count("get me ten articles about NLP") == 10

    def test_word_count_three(self, policy):
        assert policy.extract_requested_paper_count("find three papers on climate") == 3

    def test_year_not_confused_with_count(self, policy):
        """'last 3 years' should NOT return 3 — 3 is tied to 'years', not 'papers'."""
        assert policy.extract_requested_paper_count("papers from the last 3 years") is None

    def test_few_papers(self, policy):
        assert policy.extract_requested_paper_count("find a few papers about NLP") == 3

    def test_several_papers(self, policy):
        assert policy.extract_requested_paper_count("find several papers on climate") == 7

    def test_no_count(self, policy):
        assert policy.extract_requested_paper_count("find papers on AI") is None

    def test_empty_input(self, policy):
        assert policy.extract_requested_paper_count("") is None

    def test_none_input(self, policy):
        assert policy.extract_requested_paper_count(None) is None

    def test_count_clamped_to_50(self, policy):
        """Counts above 50 should be clamped to 50."""
        assert policy.extract_requested_paper_count("find 100 papers on NLP") == 50

    def test_digit_with_intermediary_words(self, policy):
        """'5 more papers' — digit not directly adjacent to 'papers'."""
        assert policy.extract_requested_paper_count("find 5 more papers") == 5

    def test_year_in_between_excludes_count(self, policy):
        """'3 papers from last 2 years' — 3 is tied to papers, should return 3."""
        assert policy.extract_requested_paper_count("3 papers from last 2 years") == 3


# ── is_low_information_query ────────────────────────────────────────────


class TestIsLowInformationQuery:
    """Test DiscussionPolicy.is_low_information_query static method."""

    def test_low_info_my_project(self, policy):
        assert policy.is_low_information_query("papers about my project") is True

    def test_low_info_more_papers(self, policy):
        assert policy.is_low_information_query("more papers") is True

    def test_low_info_recent_articles(self, policy):
        assert policy.is_low_information_query("find me some recent articles") is True

    def test_substantive_topic(self, policy):
        assert policy.is_low_information_query("machine learning in healthcare") is False

    def test_substantive_climate(self, policy):
        assert policy.is_low_information_query("climate adaptation policy") is False

    def test_substantive_transformer(self, policy):
        assert policy.is_low_information_query("transformer architectures") is False

    def test_empty_string(self, policy):
        assert policy.is_low_information_query("") is True

    def test_none_string(self, policy):
        assert policy.is_low_information_query(None) is True

    def test_only_stopwords(self, policy):
        assert policy.is_low_information_query("the a an") is True

    def test_single_substantive_word(self, policy):
        assert policy.is_low_information_query("CRISPR") is False

    def test_numbers_ignored_as_non_alpha(self, policy):
        """Digit-only tokens are filtered by the alpha regex."""
        assert policy.is_low_information_query("3 papers about this topic") is True


# ── resolve_search_context ──────────────────────────────────────────────


class TestResolveSearchContext:
    """Test DiscussionPolicy.resolve_search_context priority chain."""

    def test_explicit_topic_wins(self, policy):
        result = policy.resolve_search_context(
            user_message="find papers on transformer architectures",
            topic_hint="deep learning",
            last_search_topic="GANs",
            project_context="AI Research",
        )
        assert result.source == "explicit_user_topic"
        assert "transformer" in result.resolved_topic.lower()

    def test_memory_hint_when_low_info(self, policy):
        result = policy.resolve_search_context(
            user_message="find me more papers",
            topic_hint="neural machine translation",
            last_search_topic="",
            project_context="",
        )
        assert result.source == "memory_topic_hint"
        assert result.resolved_topic == "neural machine translation"

    def test_last_search_topic_fallback(self, policy):
        result = policy.resolve_search_context(
            user_message="find more papers about my research",
            topic_hint="",
            last_search_topic="reinforcement learning",
            project_context="AI Project",
        )
        assert result.source == "last_search_topic"
        assert result.resolved_topic == "reinforcement learning"

    def test_project_context_fallback(self, policy):
        result = policy.resolve_search_context(
            user_message="find me some papers",
            topic_hint="",
            last_search_topic="",
            project_context="Climate Change Research",
        )
        assert result.source == "project_context"
        assert result.resolved_topic == "Climate Change Research"

    def test_fallback_default(self, policy):
        result = policy.resolve_search_context(
            user_message="find me some papers",
            topic_hint="",
            last_search_topic="",
            project_context="",
        )
        assert result.source == "fallback_default"

    def test_deictic_marker_forces_fallthrough(self, policy):
        """'this topic' should cause fallthrough even if cleaned text looks substantive."""
        result = policy.resolve_search_context(
            user_message="find papers on this topic",
            topic_hint="quantum computing",
            last_search_topic="",
            project_context="",
        )
        # "this topic" is deictic and also low-info, so it should fall through
        assert result.is_deictic is True
        assert result.source == "memory_topic_hint"

    def test_relative_only_forces_fallthrough(self, policy):
        """'another 3 papers' is relative-only and should fall through."""
        result = policy.resolve_search_context(
            user_message="find another 3 papers",
            topic_hint="",
            last_search_topic="graph neural networks",
            project_context="",
        )
        assert result.source == "last_search_topic"

    def test_topic_truncated_to_300(self, policy):
        long_topic = "x" * 500
        result = policy.resolve_search_context(
            user_message=f"find papers on {long_topic}",
            topic_hint="",
            last_search_topic="",
            project_context="",
        )
        assert len(result.resolved_topic) <= 300


# ── is_direct_paper_search_request (intent classification) ──────────────


class TestIsDirectPaperSearchRequest:
    """Test DiscussionPolicy.is_direct_paper_search_request."""

    def test_find_papers(self, policy):
        assert policy.is_direct_paper_search_request("find me papers on NLP") is True

    def test_search_articles(self, policy):
        assert policy.is_direct_paper_search_request("search for articles about AI") is True

    def test_could_you_find(self, policy):
        assert policy.is_direct_paper_search_request("could you find papers on transformers") is True

    def test_please_search(self, policy):
        assert policy.is_direct_paper_search_request("please search for studies on climate") is True

    def test_library_request_excluded(self, policy):
        """Requests mentioning 'my library' should NOT match."""
        assert policy.is_direct_paper_search_request("find papers in my library") is False

    def test_general_question_not_search(self, policy):
        assert policy.is_direct_paper_search_request("what is machine learning?") is False

    def test_no_paper_term_not_search(self, policy):
        """Search verb without paper-like noun should not match."""
        assert policy.is_direct_paper_search_request("find me information about NLP") is False

    def test_empty_string(self, policy):
        assert policy.is_direct_paper_search_request("") is False

    def test_none_input(self, policy):
        assert policy.is_direct_paper_search_request(None) is False


# ── detect_deictic_markers ──────────────────────────────────────────────


class TestDeicticMarkers:
    """Test deictic marker detection via _DEICTIC_MARKERS used in resolve_search_context."""

    def test_this_topic_detected(self, policy):
        result = policy.resolve_search_context("find papers on this topic")
        assert result.is_deictic is True

    def test_that_area_detected(self, policy):
        result = policy.resolve_search_context("find studies in that area")
        assert result.is_deictic is True

    def test_this_field_detected(self, policy):
        result = policy.resolve_search_context("find papers in this field")
        assert result.is_deictic is True

    def test_no_deictic_marker(self, policy):
        result = policy.resolve_search_context("find papers on machine learning")
        assert result.is_deictic is False

    def test_deictic_with_substantive_content_still_flagged(self, policy):
        """Deictic flag is set based on marker presence, independent of topic content."""
        result = policy.resolve_search_context(
            "find papers on this topic of quantum computing"
        )
        assert result.is_deictic is True


# ── user_requested_open_access ──────────────────────────────────────────


class TestUserRequestedOpenAccess:
    """Test DiscussionPolicy.user_requested_open_access static method."""

    def test_open_access(self, policy):
        assert policy.user_requested_open_access("find open access papers on AI") is True

    def test_oa_only(self, policy):
        assert policy.user_requested_open_access("search OA only papers") is True

    def test_with_pdf(self, policy):
        assert policy.user_requested_open_access("papers with pdf on NLP") is True

    def test_no_oa_marker(self, policy):
        assert policy.user_requested_open_access("find papers on AI") is False

    def test_empty_input(self, policy):
        assert policy.user_requested_open_access("") is False

    def test_none_input(self, policy):
        assert policy.user_requested_open_access(None) is False


# ── user_requested_detailed_response ────────────────────────────────────


class TestUserRequestedDetailedResponse:
    """Test DiscussionPolicy.user_requested_detailed_response static method."""

    def test_in_detail(self, policy):
        assert policy.user_requested_detailed_response("explain this in detail") is True

    def test_comprehensive(self, policy):
        assert policy.user_requested_detailed_response("give me a comprehensive review") is True

    def test_step_by_step(self, policy):
        assert policy.user_requested_detailed_response("explain step by step") is True

    def test_deep_dive(self, policy):
        assert policy.user_requested_detailed_response("do a deep dive on this") is True

    def test_normal_message(self, policy):
        assert policy.user_requested_detailed_response("explain this concept") is False

    def test_empty_input(self, policy):
        assert policy.user_requested_detailed_response("") is False

    def test_none_input(self, policy):
        assert policy.user_requested_detailed_response(None) is False


# ── is_project_update_request ───────────────────────────────────────────


class TestIsProjectUpdateRequest:
    """Test DiscussionPolicy.is_project_update_request."""

    def test_update_keywords(self, policy):
        assert policy.is_project_update_request("update the project keywords") is True

    def test_change_objectives(self, policy):
        assert policy.is_project_update_request("change the project objectives") is True

    def test_add_keyword(self, policy):
        assert policy.is_project_update_request("add keyword machine learning") is True

    def test_edit_description(self, policy):
        assert policy.is_project_update_request("edit the project description") is True

    def test_not_project_update(self, policy):
        assert policy.is_project_update_request("find papers on machine learning") is False

    def test_empty_input(self, policy):
        assert policy.is_project_update_request("") is False

    def test_none_input(self, policy):
        assert policy.is_project_update_request(None) is False


# ── build_decision (integration of multiple policy components) ──────────


class TestBuildDecision:
    """Test DiscussionPolicy.build_decision end-to-end routing."""

    def test_direct_search_intent(self, policy):
        decision = policy.build_decision(
            user_message="find papers on deep learning",
            search_tool_available=True,
        )
        assert decision.intent == "direct_search"
        assert decision.force_tool == "search_papers"
        assert decision.search is not None
        assert decision.search.count == 5  # default

    def test_direct_search_with_count_and_years(self, policy):
        decision = policy.build_decision(
            user_message="find 10 papers on NLP from the last 3 years",
            search_tool_available=True,
        )
        assert decision.intent == "direct_search"
        assert decision.search.count == 10
        assert decision.search.year_from == CURRENT_YEAR - 2
        assert decision.search.year_to == CURRENT_YEAR

    def test_project_update_intent(self, policy):
        decision = policy.build_decision(
            user_message="update the project keywords to include NLP",
        )
        assert decision.intent == "project_update"
        assert decision.action_plan is not None
        assert "search_papers" in decision.action_plan.blocked_tools

    def test_general_intent_fallback(self, policy):
        decision = policy.build_decision(
            user_message="what is machine learning?",
        )
        assert decision.intent == "general"

    def test_search_without_tool_available(self, policy):
        decision = policy.build_decision(
            user_message="find papers on deep learning",
            search_tool_available=False,
        )
        assert decision.intent == "direct_search"
        assert decision.force_tool is None

    def test_should_force_tool_true(self, policy):
        decision = policy.build_decision(
            user_message="find papers on transformers",
            search_tool_available=True,
        )
        assert decision.should_force_tool("search_papers") is True
        assert decision.should_force_tool("other_tool") is False

    def test_should_force_tool_false_when_no_search(self, policy):
        decision = policy.build_decision(
            user_message="what is NLP?",
        )
        assert decision.should_force_tool("search_papers") is False

    def test_derive_topic_fn_transforms_search_query(self, policy):
        """When derive_topic_fn is supplied, build_decision should use its output as the search query."""
        decision = policy.build_decision(
            user_message="find papers on deep learning",
            search_tool_available=True,
            derive_topic_fn=lambda q: f"DERIVED({q})",
        )
        assert decision.intent == "direct_search"
        assert decision.search is not None
        assert decision.search.query.startswith("DERIVED(")


# ── _RELATIVE_ONLY_RE ───────────────────────────────────────────────────


class TestRelativeOnlyPattern:
    """Test the _RELATIVE_ONLY_RE regex via resolve_search_context."""

    def test_another_papers(self, policy):
        result = policy.resolve_search_context("find another 3 papers")
        assert result.is_relative_only is True

    def test_more_papers(self, policy):
        """'more papers' after cleaning becomes empty — falls through to fallback.
        The relative-only regex is checked on the cleaned text, which in this case
        is empty because _clean_search_request_text strips 'more papers' entirely."""
        result = policy.resolve_search_context("find more papers")
        # cleaned_user_text is empty, so is_relative_only is False
        assert result.cleaned_user_text == ""
        assert result.source == "fallback_default"

    def test_additional_5_papers_is_relative(self, policy):
        """'additional 5 papers' survives cleaning and matches relative-only."""
        result = policy.resolve_search_context("could you find additional 5 papers")
        assert result.is_relative_only is True

    def test_a_few_more(self, policy):
        result = policy.resolve_search_context("find a few more papers")
        assert result.is_relative_only is True

    def test_substantive_not_relative(self, policy):
        result = policy.resolve_search_context("find papers on CRISPR gene editing")
        assert result.is_relative_only is False


# ── build_search_query ──────────────────────────────────────────────────


class TestBuildSearchQuery:
    """Test DiscussionPolicy.build_search_query convenience method."""

    def test_basic_topic_passthrough(self, policy):
        """A substantive topic should pass through unchanged."""
        query = policy.build_search_query("find papers on transformer architectures")
        assert "transformer" in query.lower()

    def test_derive_topic_fn_overrides(self, policy):
        """When derive_topic_fn returns a value, it should replace the resolved topic."""
        query = policy.build_search_query(
            "find papers on deep learning",
            derive_topic_fn=lambda q: "overridden topic",
        )
        assert query == "overridden topic"

    def test_derive_topic_fn_returning_none_keeps_original(self, policy):
        """When derive_topic_fn returns None, the original resolved topic is kept."""
        query = policy.build_search_query(
            "find papers on deep learning",
            derive_topic_fn=lambda q: None,
        )
        assert "deep learning" in query.lower()

    def test_empty_query_fallback(self, policy):
        """An empty/low-info query with no context should fall back to the default string."""
        query = policy.build_search_query("")
        assert query == "academic research papers"

    def test_truncation_to_300_chars(self, policy):
        """Extremely long topics should be truncated to 300 characters."""
        long_topic = "a" * 500
        query = policy.build_search_query(f"find papers on {long_topic}")
        assert len(query) <= 300


# ── _clean_search_request_text ──────────────────────────────────────────


class TestCleanSearchRequestText:
    """Test DiscussionPolicy._clean_search_request_text static method."""

    def test_strips_search_verb_prefix(self, policy):
        """'find me ...' prefix should be removed."""
        result = DiscussionPolicy._clean_search_request_text(
            "find me papers on quantum computing"
        )
        assert "quantum computing" in result.lower()
        assert not result.lower().startswith("find")

    def test_strips_could_you_search_prefix(self, policy):
        """'could you search ...' prefix should be removed."""
        result = DiscussionPolicy._clean_search_request_text(
            "could you search for papers about climate change"
        )
        assert "climate change" in result.lower()
        assert "could" not in result.lower()

    def test_strips_paper_nouns(self, policy):
        """Paper-like nouns followed by 'on/about' should be removed."""
        result = DiscussionPolicy._clean_search_request_text(
            "find papers about neural networks"
        )
        assert "neural networks" in result.lower()
        assert "papers" not in result.lower()

    def test_strips_trailing_year_filter(self, policy):
        """Trailing year ranges like 'from 2020 to 2024' should be removed."""
        result = DiscussionPolicy._clean_search_request_text(
            "find papers on AI from 2020 to 2024"
        )
        assert "2020" not in result
        assert "2024" not in result
        assert "ai" in result.lower()

    def test_preserves_substantive_topic(self, policy):
        """The substantive topic content should survive cleaning."""
        result = DiscussionPolicy._clean_search_request_text(
            "please search for recent articles about graph neural networks"
        )
        assert "graph neural networks" in result.lower()
