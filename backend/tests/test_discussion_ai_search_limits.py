"""Bounded library pagination and canonical batch-search limits."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.discussion_ai.tool_orchestrator import ToolOrchestrator
from app.services.discussion_ai.tools.search_tools import BATCH_SEARCH_PAPERS_SCHEMA


def _orchestrator() -> ToolOrchestrator:
    return ToolOrchestrator(SimpleNamespace(default_model="gpt-5-mini"), MagicMock())


def _query(orchestrator: ToolOrchestrator, items: list[SimpleNamespace]) -> MagicMock:
    query = MagicMock()
    for method in ("join", "filter", "order_by", "offset", "limit"):
        getattr(query, method).return_value = query
    query.count.return_value = 30
    query.all.return_value = items
    orchestrator.db.query.return_value = query
    return query


def test_reference_library_uses_default_limit_and_reports_next_page() -> None:
    orchestrator = _orchestrator()
    reference = SimpleNamespace(
        id="ref", title="Title", authors=[], year=2025, abstract="Abstract",
        source="test", pdf_url=None, is_open_access=False, status="pending",
    )
    query = _query(orchestrator, [reference] * 10)

    # The mocked query cannot serve (reference_id, created_at) rows for scope entry times.
    with patch("app.services.discussion_ai.mixins.search_tools_mixin.project_reference_entry_times", return_value={}):
        result = orchestrator._tool_get_project_references({"project": SimpleNamespace(id="project")})

    query.limit.assert_called_once_with(10)
    query.offset.assert_called_once_with(0)
    assert result["total_count"] == 30
    assert result["returned_count"] == 10
    assert result["papers"][0]["cite_key"] == "2025title"
    assert result["truncated"] is True
    assert result["next_offset"] == 10


def test_reference_library_final_page_has_no_next_offset() -> None:
    orchestrator = _orchestrator()
    query = _query(orchestrator, [])

    result = orchestrator._tool_get_project_references(
        {"project": SimpleNamespace(id="project")}, limit=20, offset=30,
    )

    query.limit.assert_called_once_with(20)
    query.offset.assert_called_once_with(30)
    assert result["truncated"] is False
    assert result["next_offset"] is None


def test_draft_content_is_bounded_and_pagination_is_reported() -> None:
    orchestrator = _orchestrator()
    paper = SimpleNamespace(
        id="paper", title="Draft", status="draft", paper_type="research",
        abstract="Abstract", content="x" * 20000, content_json=None,
    )
    query = _query(orchestrator, [paper] * 5)
    with patch.object(orchestrator, "_latex_to_markdown", side_effect=lambda content: content):
        result = orchestrator._tool_get_project_papers(
            {"project": SimpleNamespace(id="project")}, include_content=True,
            limit=20, offset=5,
        )

    query.limit.assert_called_once_with(5)
    query.offset.assert_called_once_with(5)
    assert result["count"] == 5
    assert result["next_offset"] == 10
    assert result["truncated"] is True
    assert result["papers"][0]["content_truncated"] is True
    assert result["papers"][0]["content"].startswith("x" * 12000)
    assert "Content truncated" in result["papers"][0]["content"]
    assert len(result["papers"][0]["content"]) < 12100


def test_batch_schema_uses_only_max_results() -> None:
    topics = BATCH_SEARCH_PAPERS_SCHEMA["function"]["parameters"]["properties"]["topics"]
    assert topics["maxItems"] == 5
    assert topics["items"]["additionalProperties"] is False
    assert "limit" not in topics["items"]["properties"]
    assert topics["items"]["properties"]["max_results"]["maximum"] == 5


def test_batch_handler_respects_per_topic_max_results() -> None:
    orchestrator = _orchestrator()

    async def discover_papers(query: str, max_results: int, fast_mode: bool) -> SimpleNamespace:
        return SimpleNamespace(
            status="success", error=None,
            papers=[SimpleNamespace(
                title=f"{query} paper {index}", doi=f"{query}/{index}", authors=[],
                year=2025, abstract="Abstract", url=None, pdf_url=None, source="test",
            ) for index in range(10)],
        )

    discovery = MagicMock()
    discovery.discover_papers = AsyncMock(side_effect=discover_papers)
    discovery.close = AsyncMock()
    with (
        patch("app.services.paper_discovery_service.PaperDiscoveryService", return_value=discovery),
        patch("app.services.discussion_ai.search_cache.store_search_results") as store,
    ):
        result = orchestrator._tool_batch_search_papers({}, topics=[
            {"topic": "First", "query": "graph networks", "max_results": 1},
            {"topic": "Second", "query": "language models", "max_results": 2},
        ])

    assert result["status"] == "success"
    assert [topic["count"] for topic in result["topic_results"]] == [1, 2]
    assert len(result["action"]["payload"]["papers"]) == 3
    assert len(store.call_args.args[1]) == 3
    assert [call.kwargs["max_results"] for call in discovery.discover_papers.call_args_list] == [3, 6]


def test_batch_budget_reports_each_uncovered_topic() -> None:
    orchestrator = _orchestrator()
    orchestrator._tool_registry = MagicMock()
    orchestrator._tool_registry.execute.return_value = {
        "status": "success", "topic_results": [
            {"topic": "A", "count": 1, "status": "success"},
            {"topic": "B", "count": 1, "status": "success"},
        ],
    }
    ctx = {"user_role": "admin", "max_papers": 10, "papers_requested": 8}
    result = orchestrator._execute_tool_calls([{
        "name": "batch_search_papers", "arguments": {"topics": [
            {"topic": name, "query": name, "max_results": 5} for name in ["A", "B", "C"]
        ]},
    }], ctx)[0]["result"]
    assert [topic["max_results"] for topic in orchestrator._tool_registry.execute.call_args.args[3]["topics"]] == [1, 1]
    assert result["status"] == "partial"
    skipped = result["topic_results"][2]
    assert skipped["topic"] == "C"
    assert skipped["status"] == "skipped"
    assert "budget" in skipped["message"]
    assert "10" in skipped["message"]


def test_batch_budget_gives_each_topic_one_before_additional_results() -> None:
    orchestrator = _orchestrator()
    orchestrator._tool_registry = MagicMock()
    orchestrator._tool_registry.execute.return_value = {"status": "success"}
    orchestrator._execute_tool_calls([{
        "name": "batch_search_papers", "arguments": {"topics": [
            {"topic": str(index), "query": "search", "max_results": count}
            for index, count in enumerate([5, 1, 1])
        ]},
    }], {"user_role": "admin", "max_papers": 3})
    assert [topic["max_results"] for topic in orchestrator._tool_registry.execute.call_args.args[3]["topics"]] == [1, 1, 1]


def test_exhausted_batch_budget_reports_all_topics_skipped() -> None:
    orchestrator = _orchestrator()
    orchestrator._tool_registry = MagicMock()
    result = orchestrator._execute_tool_calls([{
        "name": "batch_search_papers", "arguments": {"topics": [
            {"topic": name, "query": name, "max_results": 5} for name in ["A", "B", "C"]
        ]},
    }], {"user_role": "admin", "max_papers": 10, "papers_requested": 10})[0]["result"]
    orchestrator._tool_registry.execute.assert_not_called()
    assert [topic["topic"] for topic in result["topic_results"]] == ["A", "B", "C"]
    assert all(topic["status"] == "skipped" and "budget" in topic["message"] for topic in result["topic_results"])


def test_partial_batch_preserves_model_budget_explanation() -> None:
    orchestrator = _orchestrator()
    message = "Searched A and B; C was skipped because the paper search budget is 2."
    tool_results = [{"name": "batch_search_papers", "result": {
        "status": "partial", "message": message,
        "topic_results": [{"topic": "C", "count": 0, "status": "skipped", "message": "Paper search budget is 2."}],
    }}]
    assert orchestrator._apply_response_budget(message, {}, tool_results) == message
    assert orchestrator._generate_tool_summary_message(tool_results) == message


def test_sync_partial_batch_returns_skipped_topics_to_model() -> None:
    orchestrator = _orchestrator()
    message = "Searched A and B; C was skipped because the paper search budget is 2."
    tool_results = [{"name": "batch_search_papers", "result": {
        "status": "partial", "message": message,
        "topic_results": [{"topic": "C", "count": 0, "status": "skipped", "message": "Paper search budget is 2."}],
    }}]
    ctx = {"user_role": "admin", "user_message": "Find papers", "channel": SimpleNamespace()}
    with (
        patch.object(orchestrator, "_classify_and_build_policy"),
        patch.object(orchestrator, "_fit_provider_messages", side_effect=lambda messages, ctx, tools: messages),
        patch.object(orchestrator, "_call_ai_with_tools", side_effect=[
            {"content": "", "tool_calls": [{"id": "batch", "name": "batch_search_papers", "arguments": {}}]},
            {"content": message, "tool_calls": []},
        ]) as provider,
        patch.object(orchestrator, "_execute_tool_calls", return_value=tool_results),
        patch.object(orchestrator, "_apply_citation_filter_for_context", side_effect=lambda text, ctx: (text, [])),
        patch.object(orchestrator, "_extract_actions", return_value=[]),
        patch.object(orchestrator, "update_memory_after_exchange"),
        patch.object(orchestrator, "_enforce_finding_papers_stage_after_search"),
        patch.object(orchestrator, "_record_quality_metrics"),
        patch.object(orchestrator, "_get_ai_memory", return_value={}),
        patch.object(orchestrator, "_save_ai_memory"),
    ):
        result = orchestrator._execute_with_tools([{"role": "user", "content": "Find papers"}], ctx)
    assert provider.call_count == 2
    assert '"status": "skipped"' in provider.call_args.args[0][-1]["content"]
    assert result["message"] == message
