"""
Deterministic filter guards for paper discovery.

These tests ensure year/OA constraints are enforced even if an upstream
provider returns out-of-policy papers.
"""

from __future__ import annotations

import pytest

from app.services.paper_discovery.config import DiscoveryConfig
from app.services.paper_discovery.interfaces import PaperEnricher, PaperRanker, PaperSearcher
from app.services.paper_discovery.models import DiscoveredPaper
from app.services.paper_discovery_service import SearchOrchestrator


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
