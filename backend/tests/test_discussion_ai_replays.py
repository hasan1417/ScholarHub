"""
Replay-style deterministic policy regression tests.

These replay fixtures lock expected routing/default behavior across different
prompt phrasings without depending on LLM text generation.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from app.services.discussion_ai.policy import DiscussionPolicy


FIXTURE_PATH = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "discussion_replays"
    / "policy_replays.json"
)


def _load_cases() -> list[dict[str, Any]]:
    with FIXTURE_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _resolve_year_symbol(value: Any, current_year: int) -> Any:
    if value == "current_year":
        return current_year
    if value == "current_year_minus_4":
        return current_year - 4
    if value == "current_year_minus_2":
        return current_year - 2
    if value == "current_year_minus_9":
        return current_year - 9
    return value


@pytest.mark.parametrize("case", _load_cases(), ids=lambda c: c.get("name", "case"))
def test_policy_replay_cases(case: dict[str, Any]) -> None:
    policy = DiscussionPolicy()
    current_year = datetime.now(timezone.utc).year

    decision = policy.build_decision(
        user_message=case["user_message"],
        topic_hint=case.get("topic_hint", ""),
        search_tool_available=case.get("search_tool_available", False),
    )

    expected = case["expect"]
    assert decision.intent == expected["intent"]
    assert decision.force_tool == expected.get("force_tool")

    expected_search = expected.get("search")
    if expected_search is None:
        assert decision.search is None
        return

    assert decision.search is not None
    assert decision.search.count == expected_search["count"]
    assert decision.search.open_access_only == expected_search["open_access_only"]
    assert decision.search.year_from == _resolve_year_symbol(expected_search.get("year_from"), current_year)
    assert decision.search.year_to == _resolve_year_symbol(expected_search.get("year_to"), current_year)

    query = decision.search.query.lower()
    for token in expected_search.get("query_contains", []):
        assert token.lower() in query
    for token in expected_search.get("query_not_contains", []):
        assert token.lower() not in query


def test_policy_replay_case_count_minimum() -> None:
    """Keep replay harness broad enough to catch routing regressions."""
    assert len(_load_cases()) >= 20
