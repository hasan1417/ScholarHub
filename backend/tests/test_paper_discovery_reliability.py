from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import app.services.paper_discovery_service as discovery_module
import app.services.paper_discovery.abstract_cache as abstract_cache
from app.services.discussion_ai.mixins.search_tools_mixin import SearchToolsMixin
from app.services.paper_discovery.abstract_cache import (
    MAX_ATTEMPTS_BEFORE_GIVEUP,
    NEGATIVE_CACHE_BASE_TTL,
    NEGATIVE_CACHE_GIVEUP_TTL,
    CachedAbstract,
    _fetch_semantic_scholar,
    _should_retry,
)
from app.services.paper_discovery.cache import LRUCache
from app.services.paper_discovery.config import DiscoveryConfig
from app.services.paper_discovery.interfaces import (
    PaperEnricher,
    PaperRanker,
    PaperSearcher,
    SourceSearchError,
)
from app.services.paper_discovery.models import DiscoveredPaper
from app.services.paper_discovery.query import QueryIntent
from app.services.paper_discovery.searchers import ArxivSearcher
from app.services.paper_discovery_service import (
    DiscoveryResult,
    PaperDiscoveryService,
    SearchOrchestrator,
    SourceStats,
)


def _paper(index: int, source: str = "test") -> DiscoveredPaper:
    return DiscoveredPaper(
        title=f"Paper {source} {index}",
        authors=["A. Author"],
        abstract="A sufficiently descriptive abstract for discovery reliability testing.",
        year=2025,
        doi=f"10.1000/{source}-{index}",
        url=f"https://example.org/{source}/{index}",
        source=source,
        relevance_score=1.0,
    )


class _Searcher(PaperSearcher):
    def __init__(
        self,
        name: str,
        papers: list[DiscoveredPaper] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.name = name
        self.papers = papers or []
        self.error = error

    def get_source_name(self) -> str:
        return self.name

    async def search(self, query: str, max_results: int, **kwargs) -> list[DiscoveredPaper]:
        _ = (query, max_results, kwargs)
        if self.error:
            raise self.error
        return list(self.papers)


class _SlowSearcher(PaperSearcher):
    def __init__(self, name: str) -> None:
        self.name = name
        self.cancelled = False

    def get_source_name(self) -> str:
        return self.name

    async def search(self, query: str, max_results: int, **kwargs) -> list[DiscoveredPaper]:
        _ = (query, max_results, kwargs)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return []


class _RecordingEnricher(PaperEnricher):
    def __init__(self) -> None:
        self.paper_count = 0

    async def enrich(self, papers: list[DiscoveredPaper]) -> None:
        self.paper_count = len(papers)


class _RecordingRanker(PaperRanker):
    def __init__(self) -> None:
        self.titles: list[str] = []

    async def rank(
        self,
        papers: list[DiscoveredPaper],
        query: str,
        **kwargs,
    ) -> list[DiscoveredPaper]:
        _ = (query, kwargs)
        self.titles = [paper.title for paper in papers]
        return list(papers)


def _orchestrator(
    searchers: list[PaperSearcher],
    *,
    enricher: PaperEnricher | None = None,
    ranker: PaperRanker | None = None,
) -> SearchOrchestrator:
    return SearchOrchestrator(
        searchers=searchers,
        enrichers=[enricher or _RecordingEnricher()],
        ranker=ranker or _RecordingRanker(),
        config=DiscoveryConfig(),
    )


class _HttpResponse:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status = status
        self.payload = {} if payload is None else payload

    async def __aenter__(self) -> "_HttpResponse":
        return self

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        _ = (exc_type, exc, traceback)

    async def json(self) -> Any:
        return self.payload


class _HttpSession:
    def __init__(self, status: int, payload: Any = None) -> None:
        self.status = status
        self.payload = payload

    def get(self, *args, **kwargs) -> _HttpResponse:
        _ = (args, kwargs)
        return _HttpResponse(self.status, self.payload)

    def post(self, *args: Any, **kwargs: Any) -> _HttpResponse:
        return self.get(*args, **kwargs)


@pytest.mark.asyncio
async def test_source_http_failure_raises_typed_error() -> None:
    searcher = ArxivSearcher(_HttpSession(503), DiscoveryConfig())  # type: ignore[arg-type]

    with pytest.raises(SourceSearchError):
        await searcher.search("query", 5)


@pytest.mark.asyncio
async def test_abstract_fetch_distinguishes_transient_and_definitive_http_statuses() -> None:
    transient = await _fetch_semantic_scholar(
        _HttpSession(429),  # type: ignore[arg-type]
        "10.1/rate-limited",
        None,
    )
    definitive = await _fetch_semantic_scholar(
        _HttpSession(404),  # type: ignore[arg-type]
        "10.1/missing",
        None,
    )

    assert transient[2] == "transient"
    assert definitive[2] == "not_found"


@pytest.mark.asyncio
async def test_discovery_distinguishes_empty_partial_and_total_outage() -> None:
    empty = await _orchestrator([_Searcher("answered")]).discover_papers("query")
    partial = await _orchestrator([
        _Searcher("answered"),
        _Searcher("down", error=SourceSearchError("network down")),
    ]).discover_papers("query")
    outage = await _orchestrator([
        _Searcher("down-1", error=SourceSearchError("network down")),
        _Searcher("down-2", error=SourceSearchError("HTTP 503")),
    ]).discover_papers("query")

    assert empty.status == "empty"
    assert partial.status == "partial"
    assert outage.status == "error"
    assert outage.error and "down-1" in outage.error and "down-2" in outage.error
    assert all(stat.status == "error" for stat in outage.source_stats)


@pytest.mark.asyncio
async def test_fast_mode_cancels_pending_tasks_and_collects_each_source_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monotonic_values = iter([0.0, 4.0, 4.0, 4.0])
    monkeypatch.setattr(
        discovery_module,
        "time",
        SimpleNamespace(time=time.time, monotonic=lambda: next(monotonic_values, 4.0)),
    )
    slow = _SlowSearcher("slow")
    ranker = _RecordingRanker()
    orchestrator = _orchestrator(
        [
            _Searcher("one", [_paper(1, "one"), _paper(2, "one")]),
            _Searcher("two", [_paper(1, "two"), _paper(2, "two")]),
            _Searcher("three", [_paper(1, "three"), _paper(2, "three")]),
            slow,
        ],
        ranker=ranker,
    )

    result = await orchestrator.discover_papers("query", max_results=3, fast_mode=True)

    assert slow.cancelled is True
    assert len(ranker.titles) == 6
    assert len(set(ranker.titles)) == 6
    assert next(stat for stat in result.source_stats if stat.source == "slow").status == "cancelled"


@pytest.mark.asyncio
async def test_enrichment_only_runs_on_ranked_capped_results() -> None:
    enricher = _RecordingEnricher()
    orchestrator = _orchestrator(
        [_Searcher("many", [_paper(index) for index in range(20)])],
        enricher=enricher,
    )

    result = await orchestrator.discover_papers("query", max_results=4)

    assert len(result.papers) == 4
    assert enricher.paper_count == 4


@pytest.mark.asyncio
async def test_source_search_starts_before_query_understanding_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    search_started = asyncio.Event()

    class _SignallingSearcher(_Searcher):
        async def search(self, query: str, max_results: int, **kwargs) -> list[DiscoveredPaper]:
            search_started.set()
            return await super().search(query, max_results, **kwargs)

    async def _understand(query: str) -> QueryIntent:
        await asyncio.wait_for(search_started.wait(), timeout=0.2)
        return QueryIntent(interpreted_query=query)

    monkeypatch.setattr(discovery_module, "understand_query", _understand)
    config = DiscoveryConfig(total_timeout=1.0)
    orchestrator = SearchOrchestrator(
        [_SignallingSearcher("source", [_paper(1)])],
        [_RecordingEnricher()],
        _RecordingRanker(),
        config,
    )
    service = PaperDiscoveryService(
        orchestrator=orchestrator,
        session=MagicMock(),
        config=config,
        owns_session=False,
    )

    result = await service.discover_papers("discovery reliability testing", fast_mode=True)

    assert search_started.is_set()
    assert result.status == "success"


@pytest.mark.asyncio
async def test_total_timeout_covers_complete_discovery_operation() -> None:
    class _SlowOrchestrator:
        async def discover_papers(self, *args, **kwargs):
            _ = (args, kwargs)
            await asyncio.Event().wait()

    config = DiscoveryConfig(total_timeout=0.01)
    service = PaperDiscoveryService(
        orchestrator=_SlowOrchestrator(),  # type: ignore[arg-type]
        session=MagicMock(),
        config=config,
        owns_session=False,
    )

    result = await service.discover_papers("query", fast_mode=True)

    assert result.status == "error"
    assert result.error and "timed out" in result.error.lower()


def test_abstract_negative_cache_retries_transient_failures_with_backoff() -> None:
    now = datetime.now(timezone.utc)
    recent = CachedAbstract(
        doi="10.1/recent",
        abstract=None,
        source=None,
        status="unavailable",
        attempts=1,
        fetched_at=now,
    )
    due = CachedAbstract(
        doi="10.1/due",
        abstract=None,
        source=None,
        status="unavailable",
        attempts=2,
        fetched_at=now - NEGATIVE_CACHE_BASE_TTL * 3,
    )
    exhausted = CachedAbstract(
        doi="10.1/exhausted",
        abstract=None,
        source=None,
        status="unavailable",
        attempts=MAX_ATTEMPTS_BEFORE_GIVEUP,
        fetched_at=now - timedelta(days=30),
    )
    cooling_down = CachedAbstract(
        doi="10.1/cooling-down",
        abstract=None,
        source=None,
        status="unavailable",
        attempts=MAX_ATTEMPTS_BEFORE_GIVEUP,
        fetched_at=now - NEGATIVE_CACHE_GIVEUP_TTL / 2,
    )
    definitive = CachedAbstract(
        doi="10.1/missing",
        abstract=None,
        source=None,
        status="not_found",
        attempts=1,
        fetched_at=now - timedelta(days=30),
    )

    assert _should_retry(recent, now) is False
    assert _should_retry(due, now) is True
    assert _should_retry(exhausted, now) is True
    assert _should_retry(cooling_down, now) is False
    assert _should_retry(definitive, now) is False


@pytest.mark.asyncio
async def test_lru_set_replaces_existing_value() -> None:
    cache = LRUCache()
    await cache.set("key", "fallback")
    await cache.set("key", "fresh")

    assert await cache.get("key") == "fresh"


class _SemanticSearchHarness(SearchToolsMixin):
    def __init__(self, db: object) -> None:
        self.db = db

    def _set_recent_papers(
        self,
        ctx: dict[str, object],
        papers: list[dict[str, object]],
        *,
        search_id: str,
    ) -> None:
        ctx["recent_papers"] = papers
        ctx["last_search_id"] = search_id


def test_search_tool_preserves_total_outage_status(monkeypatch: pytest.MonkeyPatch) -> None:
    class _FailedDiscoveryService:
        async def discover_papers(self, **kwargs) -> DiscoveryResult:
            _ = kwargs
            return DiscoveryResult(
                status="error",
                error="All paper sources failed",
                source_stats=[SourceStats(source="arxiv", status="error")],
            )

        async def close(self) -> None:
            return None

    monkeypatch.setattr(discovery_module, "PaperDiscoveryService", _FailedDiscoveryService)
    query_result = MagicMock()
    query_result.join.return_value.filter.return_value.all.return_value = []
    db = MagicMock()
    db.query.return_value = query_result
    harness = _SemanticSearchHarness(db)

    result = harness._tool_search_papers(
        {"project": SimpleNamespace(id=uuid4(), title="Project", keywords=[])},
        query="reliability",
    )

    assert result["status"] == "error"
    assert "Found" not in result["message"]
    assert result["action"]["payload"]["papers"] == []


def test_semantic_search_returns_reference_and_project_reference_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference_id = uuid4()
    project_reference_id = uuid4()
    query_result = MagicMock()
    query_result.join.return_value.filter.return_value.count.return_value = 1
    execution_result = MagicMock()
    execution_result.fetchall.return_value = [
        (
            reference_id,
            project_reference_id,
            "Title",
            ["Author"],
            2025,
            "10.1/test",
            "Abstract",
            "Journal",
            None,
            False,
            0.91,
        )
    ]
    db = MagicMock()
    db.query.return_value = query_result
    db.execute.return_value = execution_result
    embedding_service = MagicMock()
    embedding_service.embed = AsyncMock(return_value=[0.1, 0.2])
    monkeypatch.setattr(
        "app.services.embedding_service.get_embedding_service",
        lambda: embedding_service,
    )
    harness = _SemanticSearchHarness(db)

    result = harness._tool_semantic_search_library(
        {"project": SimpleNamespace(id=uuid4())},
        query="topic",
    )

    sql = str(db.execute.call_args.args[0])
    assert "r.id AS reference_id" in sql
    assert result["papers"][0]["reference_id"] == str(reference_id)
    assert result["papers"][0]["project_reference_id"] == str(project_reference_id)


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", [False, True])
@pytest.mark.parametrize("is_manual", [False, True])
async def test_optional_sources_are_registered_only_when_configured(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    configured: bool,
    is_manual: bool,
) -> None:
    monkeypatch.delenv("CORE_API_KEY", raising=False)
    monkeypatch.setattr(discovery_module, "_logged_disabled_sources", set())
    if configured:
        monkeypatch.setenv("CORE_API_KEY", "test-key")
    caplog.set_level("INFO", logger=discovery_module.__name__)
    key = "test-key" if configured else None
    for _ in range(2):
        searchers = discovery_module._build_default_searchers(
            MagicMock(), DiscoveryConfig(), sciencedirect_api_key=key,
            serpapi_key=key, is_manual=is_manual,
        )
    names = {searcher.get_source_name() for searcher in searchers}
    assert ("sciencedirect" in names) is configured
    assert ("core" in names) is configured
    assert ("google_scholar" in names) is (configured and is_manual)
    assert {"arxiv", "semantic_scholar", "crossref", "pubmed", "openalex", "europe_pmc"} <= names
    disabled_logs = [record for record in caplog.records if "Optional paper sources disabled" in record.message]
    assert len(disabled_logs) == (0 if configured else 1)
    for searcher in searchers:
        monkeypatch.setattr(searcher, "search", AsyncMock(return_value=[]))
    result = await _orchestrator(searchers).discover_papers("query")
    assert result.status == "empty"
    assert all(stat.status == "success" for stat in result.source_stats)


@pytest.mark.asyncio
@pytest.mark.parametrize("fetcher,payload", [
    ("_fetch_elsevier", {"full-text-retrieval-response": {"coredata": {}}}),
    ("_fetch_core", {"results": []}),
    ("_fetch_core", {"results": [{"abstract": ""}]}),
    ("_fetch_semantic_scholar", {"abstract": None}),
    ("_fetch_semantic_scholar_batch", [{"abstract": ""}]),
    ("_fetch_semantic_scholar_batch", [None]),
    ("_fetch_serpapi_snippet", {"organic_results": []}),
    ("_fetch_serpapi_snippet", {"organic_results": [{"snippet": ""}]}),
])
@pytest.mark.parametrize("http_status,expected", [(200, "not_found"), (429, "transient"), (503, "transient")])
async def test_abstract_fetchers_classify_successful_negatives(
    fetcher: str, payload: Any, http_status: int, expected: str,
) -> None:
    session = _HttpSession(http_status, payload)
    doi = "10.1/negative"
    fetch = getattr(abstract_cache, fetcher)
    if fetcher == "_fetch_semantic_scholar_batch":
        result = (await fetch(session, [doi], "test-key"))[doi]
    elif fetcher == "_fetch_serpapi_snippet":
        result = await fetch(session, doi, "Paper title for query", "test-key")
    else:
        result = await fetch(session, doi, "test-key")
    assert result == (None, None, expected)


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [[], ["invalid"], {"error": "upstream failure"}])
async def test_abstract_batch_malformed_or_missing_items_are_not_definitive(payload: Any) -> None:
    result = await abstract_cache._fetch_semantic_scholar_batch(
        _HttpSession(200, payload), ["10.1/missing"], None,
    )
    assert result["10.1/missing"][2] == "transient"


@pytest.mark.asyncio
@pytest.mark.parametrize("transient_source", [None, "_fetch_core", "_fetch_semantic_scholar", "_fetch_serpapi_snippet"])
async def test_abstract_not_found_requires_every_configured_fetcher_to_agree(
    monkeypatch: pytest.MonkeyPatch, transient_source: str | None,
) -> None:
    for key in ("CORE_API_KEY", "SCIENCEDIRECT_API_KEY", "SERPAPI_KEY"):
        monkeypatch.setenv(key, "test-key")
    for name in ("_fetch_elsevier", "_fetch_core", "_fetch_semantic_scholar", "_fetch_serpapi_snippet"):
        outcome = "transient" if name == transient_source else "not_found"
        monkeypatch.setattr(abstract_cache, name, AsyncMock(return_value=(None, None, outcome)))
    result = await abstract_cache.fetch_one(MagicMock(), "10.1/missing", "Paper title")
    assert result[2] == ("not_found" if transient_source is None else "transient")


@pytest.mark.asyncio
async def test_definitive_abstract_negative_does_not_repeat_metered_fetch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("CORE_API_KEY", "SCIENCEDIRECT_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SERPAPI_KEY", "test-key")
    cached: dict[str, CachedAbstract] = {}

    def lookup(db: object, dois: list[str]) -> dict[str, CachedAbstract]:
        return {doi: cached[doi] for doi in dois if doi in cached}

    def upsert(db: object, records: list[CachedAbstract]) -> None:
        cached.update({record.doi: record for record in records})

    monkeypatch.setattr(abstract_cache, "bulk_lookup", lookup)
    monkeypatch.setattr(abstract_cache, "bulk_upsert", upsert)
    serpapi = AsyncMock(wraps=abstract_cache._fetch_serpapi_snippet)
    monkeypatch.setattr(abstract_cache, "_fetch_serpapi_snippet", serpapi)
    session = MagicMock()
    session.post.return_value = _HttpResponse(200, [{"abstract": None}])
    session.get.return_value = _HttpResponse(200, {"organic_results": []})
    paper = _paper(1)
    paper.abstract = None
    for _ in range(2):
        await abstract_cache.fetch_missing(session, MagicMock(), [paper])
    assert cached[paper.doi].status == "not_found"
    serpapi.assert_awaited_once()


@pytest.mark.asyncio
async def test_fast_mode_drains_all_already_completed_sources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_module, "time", SimpleNamespace(time=time.time, monotonic=lambda: 4.0))
    ticks = iter([0.0])
    monkeypatch.setattr(discovery_module.time, "monotonic", lambda: next(ticks, 4.0))
    ranker = _RecordingRanker()
    slow = _SlowSearcher("slow")
    orchestrator = _orchestrator([
        *[_Searcher(str(index), [_paper(index, str(index))]) for index in range(6)], slow,
    ], ranker=ranker)
    result = await orchestrator.discover_papers("query", max_results=1, fast_mode=True)
    assert len(ranker.titles) == 6
    assert sum(stat.status == "success" for stat in result.source_stats) == 6
    assert next(stat for stat in result.source_stats if stat.source == "slow").status == "cancelled"
    assert slow.cancelled


@pytest.mark.asyncio
async def test_outer_cancellation_during_progress_callback_cleans_up_and_propagates() -> None:
    callback_started = asyncio.Event()
    slow = _SlowSearcher("slow")

    async def progress(event: dict[str, Any]) -> None:
        if event["type"] == "source_complete":
            callback_started.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(_orchestrator([
        _Searcher("completed", [_paper(1)]), slow,
    ]).discover_papers("query", progress_callback=progress))
    await asyncio.wait_for(callback_started.wait(), timeout=1.0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert slow.cancelled


@pytest.mark.asyncio
@pytest.mark.parametrize("candidate_count,expected_count", [(4, 0), (5, 5), (6, 5)])
async def test_minimum_results_matches_main_rule(candidate_count: int, expected_count: int) -> None:
    papers = [_paper(index) for index in range(candidate_count)]
    for paper in papers:
        paper.relevance_score = 0.1
    result = await _orchestrator([_Searcher("source", papers)]).discover_papers("query")
    assert len(result.papers) == expected_count


@pytest.mark.asyncio
@pytest.mark.parametrize("search_info", [{"total_results": 0}, {"organic_results_state": "Fully empty"}])
async def test_serpapi_successful_empty_error_message_is_definitive(search_info: dict[str, object]) -> None:
    result = await abstract_cache._fetch_serpapi_snippet(
        _HttpSession(200, {
            "search_metadata": {"status": "Success"},
            "search_information": search_info,
            "error": "Google hasn't returned any results for this query.",
        }),
        "10.1/missing", "Missing paper title", "test-key",
    )
    assert result[2] == "not_found"


@pytest.mark.asyncio
async def test_serpapi_upstream_error_is_not_a_definitive_negative() -> None:
    result = await abstract_cache._fetch_serpapi_snippet(
        _HttpSession(200, {"search_metadata": {"status": "Error"}, "error": "Upstream search failed"}),
        "10.1/missing", "Missing paper title", "test-key",
    )
    assert result[2] == "transient"
