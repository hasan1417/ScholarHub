"""
Deterministic filter guards for paper discovery.

These tests ensure year/OA constraints are enforced even if an upstream
provider returns out-of-policy papers.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.services.paper_discovery.config import DiscoveryConfig
from app.services.paper_discovery.interfaces import PaperEnricher, PaperRanker, PaperSearcher
from app.services.paper_discovery.models import DiscoveredPaper
from app.services.paper_discovery_service import DiscoveryResult, PaperDiscoveryService, SearchOrchestrator


def _paper(
    *,
    title: str,
    year: int | None,
    source: str = "arxiv",
    doi: str | None = None,
    is_open_access: bool = False,
    pdf_url: str | None = None,
    open_access_url: str | None = None,
) -> DiscoveredPaper:
    return DiscoveredPaper(
        title=title,
        authors=["A. Author"],
        abstract="Test abstract",
        year=year,
        doi=doi,
        url=f"https://example.org/{title.replace(' ', '_')}",
        source=source,
        is_open_access=is_open_access,
        pdf_url=pdf_url,
        open_access_url=open_access_url,
        relevance_score=1.0,
    )


class _FakeSearcher(PaperSearcher):
    def __init__(self, name: str, papers: list[DiscoveredPaper]):
        self._name = name
        self._papers = papers

    def get_source_name(self) -> str:
        return self._name

    async def search(self, query: str, max_results: int, **kwargs) -> list[DiscoveredPaper]:
        _ = (query, max_results, kwargs)
        # Intentionally ignore filters to emulate inconsistent provider behavior.
        return list(self._papers)


class _NoopEnricher(PaperEnricher):
    async def enrich(self, papers: list[DiscoveredPaper]) -> None:
        _ = papers


class _IdentityRanker(PaperRanker):
    async def rank(self, papers: list[DiscoveredPaper], query: str, **kwargs) -> list[DiscoveredPaper]:
        _ = (query, kwargs)
        return list(papers)


@pytest.mark.asyncio
async def test_hard_year_filter_removes_out_of_range_and_unknown_years():
    searcher = _FakeSearcher(
        "mixed",
        [
            _paper(title="Old Study", year=2018, doi="10.1/old"),
            _paper(title="In Range 1", year=2022, doi="10.1/in1"),
            _paper(title="In Range 2", year=2024, doi="10.1/in2"),
            _paper(title="Unknown Year", year=None, doi="10.1/unknown"),
            _paper(title="Future Out", year=2027, doi="10.1/future"),
        ],
    )
    orchestrator = SearchOrchestrator(
        searchers=[searcher],
        enrichers=[_NoopEnricher()],
        ranker=_IdentityRanker(),
        config=DiscoveryConfig(),
    )

    result = await orchestrator.discover_papers(
        query="social media academic performance",
        max_results=10,
        year_from=2022,
        year_to=2026,
        open_access_only=False,
    )

    assert [p.title for p in result.papers] == ["In Range 1", "In Range 2"]
    assert all(2022 <= int(p.year) <= 2026 for p in result.papers)


@pytest.mark.asyncio
async def test_hard_open_access_filter_removes_non_oa_results():
    searcher = _FakeSearcher(
        "oa-mixed",
        [
            _paper(title="Non OA", year=2024, doi="10.2/non-oa", is_open_access=False),
            _paper(
                title="OA with PDF",
                year=2024,
                doi="10.2/oa-pdf",
                is_open_access=True,
                pdf_url="https://example.org/paper.pdf",
            ),
            _paper(
                title="OA with URL",
                year=2023,
                doi="10.2/oa-url",
                open_access_url="https://example.org/open",
            ),
        ],
    )
    orchestrator = SearchOrchestrator(
        searchers=[searcher],
        enrichers=[_NoopEnricher()],
        ranker=_IdentityRanker(),
        config=DiscoveryConfig(),
    )

    result = await orchestrator.discover_papers(
        query="open access topic",
        max_results=10,
        open_access_only=True,
    )

    assert [p.title for p in result.papers] == ["OA with PDF", "OA with URL"]
    assert all(bool(p.is_open_access or p.pdf_url or p.open_access_url) for p in result.papers)


@pytest.mark.asyncio
async def test_google_scholar_searcher_is_manual_only():
    manual_service = PaperDiscoveryService(config=DiscoveryConfig(serpapi_key="test-key"), is_manual=True)
    auto_service = PaperDiscoveryService(config=DiscoveryConfig(serpapi_key="test-key"), is_manual=False)

    try:
        manual_sources = [searcher.get_source_name() for searcher in manual_service.orchestrator.searchers]
        auto_sources = [searcher.get_source_name() for searcher in auto_service.orchestrator.searchers]
    finally:
        await manual_service.close()
        await auto_service.close()

    assert "google_scholar" in manual_sources
    assert "google_scholar" not in auto_sources


@pytest.fixture
def discovery_api(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, MagicMock, MagicMock]]:
    from app.api.deps import get_current_user
    from app.api.v1 import discovery, discussion_actions
    from app.database import get_db
    import app.services.paper_discovery_service as discovery_service_module

    service = MagicMock()
    service.discover_papers = AsyncMock()
    service.close = AsyncMock()
    service.__aenter__ = AsyncMock(return_value=service)
    service.__aexit__ = AsyncMock(return_value=False)
    factory = MagicMock(return_value=service)
    monkeypatch.setattr(discovery, "PaperDiscoveryService", factory)
    monkeypatch.setattr(discovery_service_module, "PaperDiscoveryService", factory)
    monkeypatch.setattr(discussion_actions, "get_project_or_404", MagicMock())
    monkeypatch.setattr(discussion_actions, "ensure_project_member", MagicMock())
    monkeypatch.setattr(discovery.SubscriptionService, "check_feature_limit", MagicMock(return_value=(True, 0, 100)))
    increment_usage = MagicMock()
    monkeypatch.setattr(discovery.SubscriptionService, "increment_usage", increment_usage)
    monkeypatch.setattr("app.database.SessionLocal", MagicMock())

    api = FastAPI()
    api.include_router(discovery.router)
    api.include_router(discussion_actions.router)
    user = SimpleNamespace(id="test-user")
    db = MagicMock()
    api.dependency_overrides[get_current_user] = lambda: user
    api.dependency_overrides[get_db] = lambda: db
    with TestClient(api) as client:
        yield client, service, increment_usage


_DISCOVERY_JSON_ENDPOINTS = [
    ("/papers/discover", {"query": "reliable search"}),
    ("/papers/score-debug", {"query": "reliable search"}),
    ("/projects/test-project/discussion/search-references", {"query": "reliable search"}),
    (
        "/projects/test-project/discussion/batch-search-references",
        {"queries": [{"topic": "Reliability", "query": "reliable search"}]},
    ),
]


@pytest.mark.parametrize(("path", "payload"), _DISCOVERY_JSON_ENDPOINTS)
def test_discovery_json_reports_total_outage_as_503(
    discovery_api: tuple[TestClient, MagicMock, MagicMock],
    path: str,
    payload: dict[str, object],
) -> None:
    client, service, increment_usage = discovery_api
    service.discover_papers.return_value = DiscoveryResult(status="error", error="All paper sources failed")

    response = client.post(path, json=payload)

    assert response.status_code == 503
    assert response.json()["detail"] == "All paper sources failed"
    increment_usage.assert_not_called()
    if "/discussion/" in path:
        service.close.assert_awaited_once()
    else:
        service.__aexit__.assert_awaited_once()


@pytest.mark.parametrize(("path", "payload"), _DISCOVERY_JSON_ENDPOINTS)
@pytest.mark.parametrize("result_status", ["success", "partial", "empty"])
def test_discovery_json_preserves_results_and_success_fields(
    discovery_api: tuple[TestClient, MagicMock, MagicMock],
    path: str,
    payload: dict[str, object],
    result_status: str,
) -> None:
    client, service, _ = discovery_api
    papers = [] if result_status == "empty" else [_paper(title="Reliable search", year=2024)]
    result_error = "One source failed" if result_status == "partial" else None
    service.discover_papers.return_value = DiscoveryResult(papers=papers, status=result_status, error=result_error)

    response = client.post(path, json=payload)

    assert response.status_code == 200
    body = response.json()
    if path == "/papers/score-debug":
        assert body["count"] == len(papers)
        assert body["query_used"] == "reliable search"
        returned_papers = body["items"]
    else:
        assert body["total_found"] == len(papers)
        if "batch-search" in path:
            returned_papers = body["results"][0]["papers"]
            assert body["results"][0]["query"] == "reliable search"
        else:
            returned_papers = body["papers"]
            assert body["query"] == "reliable search"
    assert [paper["title"] for paper in returned_papers] == [paper.title for paper in papers]
    if path.startswith("/papers/"):
        assert body["status"] == result_status
        assert body["error"] == result_error


@pytest.mark.parametrize("timeout", [False, True])
def test_discovery_stream_reports_failure_with_frontend_error_shape(
    discovery_api: tuple[TestClient, MagicMock, MagicMock], timeout: bool,
) -> None:
    client, service, increment_usage = discovery_api
    if timeout:
        service.discover_papers.side_effect = asyncio.TimeoutError
    else:
        service.discover_papers.return_value = DiscoveryResult(status="error", error="All paper sources failed")

    response = client.post("/papers/discover/stream", json={"query": "reliable search"})
    events = [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")]

    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["message"] == (
        "Paper discovery timed out. Please try again later." if timeout else "All paper sources failed"
    )
    increment_usage.assert_not_called()
    service.__aexit__.assert_awaited_once()


@pytest.mark.parametrize("result_status", ["success", "partial", "empty"])
def test_discovery_stream_preserves_final_results_and_status(
    discovery_api: tuple[TestClient, MagicMock, MagicMock], result_status: str,
) -> None:
    client, service, increment_usage = discovery_api
    papers = [] if result_status == "empty" else [_paper(title="Reliable search", year=2024)]
    result_error = "One source failed" if result_status == "partial" else None
    service.discover_papers.return_value = DiscoveryResult(papers=papers, status=result_status, error=result_error)

    response = client.post("/papers/discover/stream", json={"query": "reliable search"})
    events = [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")]

    assert len(events) == 1
    assert events[0]["type"] == "final"
    assert events[0]["total"] == len(papers)
    assert [paper["title"] for paper in events[0]["papers"]] == [paper.title for paper in papers]
    assert events[0]["status"] == result_status
    assert events[0]["error"] == result_error
    increment_usage.assert_called_once()
