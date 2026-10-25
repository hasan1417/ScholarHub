"""Ranking and selection fixes: whole-word terms, DOI-safe dedup, absolute scores,
abstract-aware floor, project similarity, exclusion, and the institutional searchers."""

from __future__ import annotations

import asyncio
from typing import Any, List

import pytest

import app.services.paper_discovery_service as discovery_module
from app.services.paper_discovery.config import DiscoveryConfig
from app.services.paper_discovery.dedup import dedupe_papers
from app.services.paper_discovery.enrichers import CacheAbstractEnricher
from app.services.paper_discovery.interfaces import PaperRanker, PaperSearcher
from app.services.paper_discovery.models import DiscoveredPaper
from app.services.paper_discovery.query import QueryIntent, contains_term, count_term_hits
from app.services.paper_discovery.rankers import SemanticRanker, SimpleRanker
from app.services.paper_discovery.searchers import IeeeXploreSearcher, SpringerNatureSearcher
from app.services.paper_discovery_service import SearchOrchestrator

ABSTRACT = "A sufficiently descriptive abstract about the topic for ranking tests."


def _paper(title: str, *, doi: str | None = None, year: int | None = 2024, source: str = "test",
           abstract: str = ABSTRACT, score: float = 0.0) -> DiscoveredPaper:
    return DiscoveredPaper(
        title=title, authors=["A. Author"], abstract=abstract, year=year, doi=doi,
        url=None, source=source, relevance_score=score,
    )


class _Searcher(PaperSearcher):
    def __init__(self, name: str, papers: List[DiscoveredPaper]) -> None:
        self.name = name
        self.papers = papers

    def get_source_name(self) -> str:
        return self.name

    async def search(self, query: str, max_results: int, **kwargs: Any) -> List[DiscoveredPaper]:
        return list(self.papers)


class _AbstractLengthRanker(PaperRanker):
    """Scores 0.9 with an abstract and 0.1 without; records what it was asked to rank."""

    def __init__(self) -> None:
        self.calls: List[List[str]] = []
        self.kwargs: List[dict] = []

    async def rank(self, papers, query, target_text=None, target_keywords=None, **kwargs):
        self.calls.append([p.title for p in papers])
        self.kwargs.append(kwargs)
        for p in papers:
            p.relevance_score = 0.9 if p.abstract else 0.1
        return sorted(papers, key=lambda p: p.relevance_score, reverse=True)


class _FakeCacheEnricher(CacheAbstractEnricher):
    def __init__(self, abstracts: dict) -> None:
        self.abstracts = abstracts
        self.seen: List[str] = []

    async def enrich(self, papers: List[DiscoveredPaper]) -> None:
        for p in papers:
            self.seen.append(p.title)
            if not p.abstract and p.title in self.abstracts:
                p.abstract = self.abstracts[p.title]


@pytest.fixture(autouse=True)
def _no_cache_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discovery_module, "_fill_abstracts_from_cache", lambda papers: None)


# --- whole-word term matching ---------------------------------------------------

def test_terms_match_whole_words_and_plurals_only() -> None:
    assert not contains_term("heart sound classification at the start", "art")
    assert contains_term("art therapy for dementia", "art")
    assert contains_term("self-attention networks", "attention")
    assert contains_term("graph neural networks", "network")
    assert contains_term("deep learning for graph neural networks", "graph neural network")
    assert count_term_hits({"art", "therapy", "dementia"}, "heart sound therapy for party guests") == 1


# --- dedup ----------------------------------------------------------------------

def test_same_generic_title_with_different_dois_stays_separate() -> None:
    out, merged = dedupe_papers([
        _paper("Introduction", doi="10.1016/j.a.2021.001", year=2021),
        _paper("Introduction", doi="10.1007/b-2021-002", year=2021),
    ])
    assert len(out) == 2 and merged == 0


def test_part_one_and_part_two_are_not_fuzzy_merged() -> None:
    out, _ = dedupe_papers([
        _paper("Deep reinforcement learning for robotic manipulation: a survey part I", doi="10.1/x1"),
        _paper("Deep reinforcement learning for robotic manipulation: a survey part II", doi="10.1/x2"),
    ])
    assert len(out) == 2


def test_preprint_and_published_record_still_merge() -> None:
    out, merged = dedupe_papers([
        _paper("Attention is all you need", doi="10.48550/arXiv.1706.03762", year=2017, source="arxiv"),
        _paper("Attention is all you need", doi="10.5555/3295222.3295349", year=2017, source="crossref"),
        _paper("Attention is all you need", doi=None, year=2017, source="google_scholar"),
    ])
    assert len(out) == 1 and merged == 2
    assert out[0].doi == "10.5555/3295222.3295349"


def test_doi_less_record_joins_only_one_of_two_conflicting_groups() -> None:
    out, _ = dedupe_papers([
        _paper("Editorial", doi="10.1/a", year=2020),
        _paper("Editorial", doi=None, year=2020),
        _paper("Editorial", doi="10.1/b", year=2020),
    ])
    assert len(out) == 2


# --- SimpleRanker absolute scores -----------------------------------------------

@pytest.mark.asyncio
async def test_simple_ranker_score_does_not_depend_on_the_rest_of_the_batch() -> None:
    ranker = SimpleRanker(DiscoveryConfig())
    target = _paper("Graph neural networks for molecules", year=2020)
    alone = await ranker.rank([target], "graph neural network molecules", core_terms={"graph", "neural"})
    score_alone = alone[0].relevance_score

    target2 = _paper("Graph neural networks for molecules", year=2020)
    weak = [_paper(f"Unrelated topic {i}", year=2001) for i in range(5)]
    await ranker.rank([target2, *weak], "graph neural network molecules", core_terms={"graph", "neural"})
    assert target2.relevance_score == pytest.approx(score_alone)
    assert 0.0 < score_alone <= 1.0


# --- source diversity -----------------------------------------------------------

def test_diversity_cap_does_not_bury_a_much_better_paper() -> None:
    papers = [_paper(f"a{i}", source="a", score=0.9) for i in range(5)] + [
        _paper("b0", source="b", score=0.3),
        _paper("b1", source="b", score=0.29),
    ]
    out = SearchOrchestrator._apply_source_diversity(papers, max_results=5)
    titles = [p.title for p in out]
    # Cap is 2 per source; a2..a4 (0.9) must still precede the 0.3 papers.
    assert titles.index("a4") < titles.index("b0")


def test_diversity_cap_still_promotes_near_ties() -> None:
    papers = [_paper(f"a{i}", source="a", score=0.80) for i in range(4)] + [_paper("b0", source="b", score=0.75)]
    out = SearchOrchestrator._apply_source_diversity(papers, max_results=5)
    assert [p.title for p in out][:3] == ["a0", "a1", "b0"]


# --- orchestrator ---------------------------------------------------------------

def _orchestrator(papers, ranker, enrichers=None) -> SearchOrchestrator:
    return SearchOrchestrator([_Searcher("test", papers)], enrichers or [], ranker, DiscoveryConfig())


@pytest.mark.asyncio
async def test_missing_abstracts_are_fetched_and_rescored_before_the_floor() -> None:
    papers = [_paper(f"With abstract {i}") for i in range(6)] + [_paper("Publisher paper", abstract="")]
    ranker = _AbstractLengthRanker()
    enricher = _FakeCacheEnricher({"Publisher paper": ABSTRACT})
    result = await _orchestrator(papers, ranker, [enricher]).discover_papers("topic", max_results=10)
    assert "Publisher paper" in [p.title for p in result.papers]
    assert len(ranker.calls) == 2  # full pool, then the rescored shortlist
    assert enricher.seen.count("Publisher paper") == 1  # not fetched again after the cut


@pytest.mark.asyncio
async def test_paper_without_any_abstract_is_still_floored() -> None:
    papers = [_paper(f"With abstract {i}") for i in range(6)] + [_paper("No abstract anywhere", abstract="")]
    result = await _orchestrator(papers, _AbstractLengthRanker(), [_FakeCacheEnricher({})]).discover_papers(
        "topic", max_results=10,
    )
    assert "No abstract anywhere" not in [p.title for p in result.papers]


@pytest.mark.asyncio
async def test_cached_abstracts_are_filled_before_ranking(monkeypatch: pytest.MonkeyPatch) -> None:
    def fill(papers):
        for p in papers:
            if not p.abstract:
                p.abstract = ABSTRACT
    monkeypatch.setattr(discovery_module, "_fill_abstracts_from_cache", fill)
    ranker = _AbstractLengthRanker()
    papers = [_paper(f"P{i}", abstract="") for i in range(6)]
    result = await _orchestrator(papers, ranker).discover_papers("topic", max_results=10)
    assert len(result.papers) == 6
    assert all(p.relevance_score == 0.9 for p in result.papers)


@pytest.mark.asyncio
async def test_excluded_papers_never_take_result_slots() -> None:
    papers = [_paper(f"P{i}", doi=f"10.1/{i}") for i in range(8)]
    ranker = _AbstractLengthRanker()
    result = await _orchestrator(papers, ranker).discover_papers(
        "topic", max_results=5, exclude_paper=lambda p: p.doi in {"10.1/0", "10.1/1", "10.1/2"},
    )
    dois = {p.doi for p in result.papers}
    assert dois.isdisjoint({"10.1/0", "10.1/1", "10.1/2"}) and len(dois) == 5
    assert all(len(call) <= 5 for call in ranker.calls)


@pytest.mark.asyncio
async def test_profile_texts_reach_the_ranker() -> None:
    ranker = _AbstractLengthRanker()
    await _orchestrator([_paper("P")], ranker).discover_papers("topic", profile_texts=["project description"])
    assert ranker.kwargs[0]["profile_texts"] == ["project description"]


@pytest.mark.asyncio
async def test_slow_query_understanding_finishes_in_background() -> None:
    gate = asyncio.Event()

    async def slow_intent() -> QueryIntent:
        await gate.wait()
        return QueryIntent(interpreted_query="interpreted")

    task = asyncio.create_task(slow_intent())
    orchestrator = _orchestrator([_paper("P")], _AbstractLengthRanker())
    orchestrator_task = orchestrator.discover_papers("topic", query_intent_task=task)
    await asyncio.wait_for(orchestrator_task, timeout=10)
    assert not task.cancelled()
    gate.set()
    assert (await task).interpreted_query == "interpreted"


# --- SemanticRanker project similarity ------------------------------------------

class _FakeEmbeddings:
    """Embeds text onto two axes: 'graph' and 'cooking'."""

    @staticmethod
    def _vec(text: str) -> List[float]:
        t = text.lower()
        return [1.0 if "graph" in t else 0.0, 1.0 if "cooking" in t else 0.0]

    async def embed(self, text: str) -> List[float]:
        return self._vec(text)

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        return [self._vec(t) for t in texts]

    async def embed_papers(self, papers, title_key="title", abstract_key="abstract"):
        return {str(p.get("doi") or p.get("id")): self._vec(f"{p[title_key]} {p.get(abstract_key) or ''}") for p in papers}

    @staticmethod
    def cosine_similarity(a, b) -> float:
        import math
        na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(x * x for x in b))
        return 0.0 if not na or not nb else sum(x * y for x, y in zip(a, b)) / (na * nb)


class _NeutralReranker:
    async def rerank(self, query, papers, **kwargs):
        from app.services.paper_discovery.reranker import RerankedResult
        return [RerankedResult(paper=p, bi_encoder_score=0.5, cross_encoder_score=0.0, final_score=0.5) for p in papers]


@pytest.mark.asyncio
async def test_project_profile_lifts_papers_similar_to_the_project() -> None:
    ranker = SemanticRanker(DiscoveryConfig())
    ranker._embedding_service = _FakeEmbeddings()
    ranker._reranker = _NeutralReranker()
    graph = _paper("Message passing on graph data", doi="10.1/g", abstract="")
    cooking = _paper("Message passing in cooking robots", doi="10.1/c", abstract="")

    ranked = await ranker.rank([cooking, graph], "message passing", profile_texts=["graph learning project"])
    assert ranked[0].doi == "10.1/g"
    assert graph.relevance_score - cooking.relevance_score == pytest.approx(0.30, abs=0.01)


@pytest.mark.asyncio
async def test_without_profile_the_original_weights_apply() -> None:
    ranker = SemanticRanker(DiscoveryConfig())
    ranker._embedding_service = _FakeEmbeddings()
    ranker._reranker = _NeutralReranker()
    a = _paper("Message passing on graph data", doi="10.1/g", abstract="")
    b = _paper("Message passing in cooking robots", doi="10.1/c", abstract="")
    await ranker.rank([a, b], "message passing")
    assert a.relevance_score == pytest.approx(b.relevance_score)


# --- institutional searchers ------------------------------------------------------

class _FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, status: int, payload: Any) -> None:
        self.status, self.payload = status, payload
        self.params: dict = {}

    def get(self, url, params=None, **kwargs):
        self.params = params or {}
        return _FakeResponse(self.status, self.payload)


@pytest.mark.asyncio
async def test_ieee_xplore_results_are_parsed() -> None:
    session = _FakeSession(200, {"articles": [{
        "title": "Gradient-based learning applied to document recognition",
        "abstract": "Multilayer neural networks trained with back-propagation...",
        "doi": "10.1109/5.726791",
        "publication_year": "1998",
        "authors": {"authors": [{"full_name": "Y. LeCun"}, {"full_name": "L. Bottou"}]},
        "publication_title": "Proceedings of the IEEE",
        "html_url": "https://ieeexplore.ieee.org/document/726791/",
        "citing_paper_count": 40000,
        "access_type": "LOCKED",
        "pdf_url": "https://ieeexplore.ieee.org/stamp/stamp.jsp?arnumber=726791",
    }]})
    searcher = IeeeXploreSearcher(session, DiscoveryConfig(), api_key="k")
    papers = await searcher.search("document recognition", 10, year_from=1990, year_to=2000)
    assert session.params["start_year"] == 1990 and session.params["end_year"] == 2000
    [p] = papers
    assert (p.doi, p.year, p.source, p.journal) == ("10.1109/5.726791", 1998, "ieee_xplore", "Proceedings of the IEEE")
    assert p.authors == ["Y. LeCun", "L. Bottou"] and p.citations_count == 40000
    assert p.is_open_access is False and p.pdf_url is None  # locked: only via the library


@pytest.mark.asyncio
async def test_springer_nature_results_are_parsed() -> None:
    session = _FakeSession(200, {"records": [{
        "title": "ImageNet Large Scale Visual Recognition Challenge",
        "creators": [{"creator": "Russakovsky, Olga"}, {"creator": "Deng, Jia"}],
        "publicationName": "International Journal of Computer Vision",
        "doi": "10.1007/s11263-015-0816-y",
        "publicationDate": "2015-04-11",
        "openaccess": "false",
        "url": [{"format": "", "value": "http://dx.doi.org/10.1007/s11263-015-0816-y"}],
        "abstract": {"h1": "Abstract", "p": ["The ImageNet challenge is a benchmark", "in object recognition."]},
    }]})
    searcher = SpringerNatureSearcher(session, DiscoveryConfig(), api_key="k")
    papers = await searcher.search("imagenet", 10, year_from=2014)
    assert "onlinedatefrom:2014-01-01" in session.params["q"]
    [p] = papers
    assert p.authors == ["Olga Russakovsky", "Jia Deng"]
    assert (p.year, p.doi, p.source) == (2015, "10.1007/s11263-015-0816-y", "springer_nature")
    assert p.abstract == "The ImageNet challenge is a benchmark in object recognition."


@pytest.mark.asyncio
@pytest.mark.parametrize("searcher_cls", [IeeeXploreSearcher, SpringerNatureSearcher])
async def test_rejected_key_is_reported_as_rate_limited(searcher_cls) -> None:
    from app.services.paper_discovery.searchers import RateLimitError
    with pytest.raises(RateLimitError):
        await searcher_cls(_FakeSession(403, {}), DiscoveryConfig(), api_key="k").search("q", 5)


# --- project profile ----------------------------------------------------------------

def test_project_profile_lists_description_then_titles() -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from app.services.project_discovery_service import build_project_profile

    results = iter([
        [("Graph attention networks",), (None,)],   # library references
        [("Draft: GNNs for chemistry",)],           # papers being written
        [("Neural message passing",)],              # promoted discoveries
    ])
    db = MagicMock()
    for chain in ("join", "filter", "order_by"):
        getattr(db.query.return_value, chain).return_value = db.query.return_value
    db.query.return_value.all.side_effect = lambda: next(results)

    project = SimpleNamespace(id=1, title="Molecular GNNs", idea="Predict properties", scope=None, keywords=["gnn"])
    profile = build_project_profile(project, db)
    assert profile[0] == "Project title: Molecular GNNs\nResearch idea: Predict properties\nKeywords: gnn"
    assert profile[1:] == ["Graph attention networks", "Draft: GNNs for chemistry", "Neural message passing"]
