"""Side-effect declarations live on ToolSpec and drive duplicate-call protection."""

from app.services.discussion_ai.tool_orchestrator import (
    DISCUSSION_TOOL_REGISTRY,
    MUTATING_TOOLS,
    READ_ONLY_REFERENCE_TOOLS,
)
from app.services.discussion_ai.tools.registry import ToolSpec
from app.services.discussion_ai.utils import filter_duplicate_mutations

READ_ONLY = {
    "get_recent_search_results", "get_project_references", "get_reference_details",
    "search_papers", "get_related_papers", "semantic_search_library", "discover_topics",
    "batch_search_papers", "suggest_research_gaps", "recommend_methodology",
    "refine_research_question", "get_project_papers", "get_project_info",
    "get_created_artifacts", "get_channel_resources", "get_channel_papers", "export_citations",
}
MUTATING = {
    "add_to_library", "analyze_across_papers", "analyze_reference", "annotate_reference",
    "compare_papers", "create_artifact", "create_paper", "focus_on_papers", "generate_abstract",
    "generate_section_from_discussion", "trigger_search_ui", "update_paper", "update_project_info",
}


def test_every_registered_tool_is_classified_and_the_sets_are_disjoint() -> None:
    assert DISCUSSION_TOOL_REGISTRY.read_only_names == READ_ONLY
    assert DISCUSSION_TOOL_REGISTRY.mutating_names == MUTATING
    assert READ_ONLY_REFERENCE_TOOLS == READ_ONLY
    assert MUTATING_TOOLS == MUTATING
    assert not READ_ONLY & MUTATING
    assert {spec["function"]["name"] for spec in DISCUSSION_TOOL_REGISTRY.get_schema_list()} == READ_ONLY | MUTATING


def test_undeclared_tool_is_treated_as_mutating() -> None:
    spec = ToolSpec(name="brand_new_tool", schema={}, handler=lambda *_: {})
    assert spec.mutating is True


def test_duplicate_mutating_call_is_blocked_despite_key_order_and_whitespace() -> None:
    seen: set = set()
    first = [{"name": "add_to_library", "arguments": {"paper_indices": [1, 2], "note": "keep "}}]
    retry = [{"name": "add_to_library", "arguments": {"note": " keep", "paper_indices": [1, 2]}}]
    assert filter_duplicate_mutations(first, seen, MUTATING_TOOLS) == first
    assert filter_duplicate_mutations(retry, seen, MUTATING_TOOLS) == []


def test_different_arguments_and_read_only_repeats_pass() -> None:
    seen: set = set()
    calls = [
        {"name": "add_to_library", "arguments": {"paper_indices": [1]}},
        {"name": "add_to_library", "arguments": {"paper_indices": [2]}},
        {"name": "search_papers", "arguments": {"query": "x"}},
        {"name": "search_papers", "arguments": {"query": "x"}},
    ]
    assert filter_duplicate_mutations(calls, seen, MUTATING_TOOLS) == calls
