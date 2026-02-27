"""
Paper Discovery Service - Refactored with Clean Architecture
"""

import asyncio
import aiohttp
import hashlib
import logging
import os
import time
from typing import Callable, List, Dict, Any, Optional, Set
from datetime import datetime
from urllib.parse import urlencode, urljoin, urlparse, quote, parse_qs
import json
import io
import xml.etree.ElementTree as ET
import re
import inspect

from app.core.config import settings
from app.services.paper_discovery.config import DiscoveryConfig
from app.services.paper_discovery.interfaces import (
    PaperEnricher,
    PaperRanker,
    PaperSearcher,
)
from app.services.paper_discovery.models import DiscoveredPaper, PaperSource, _normalize_title
from app.services.paper_discovery.query import QueryIntent, extract_core_terms, understand_query

logger = logging.getLogger(__name__)


# ============= Concrete Implementations =============

from app.services.paper_discovery.searchers import (
    ArxivSearcher,
    CoreSearcher,
    CrossrefSearcher,
    EuropePmcSearcher,
    OpenAlexSearcher,
    PubMedSearcher,
    RateLimitError,
    ScienceDirectSearcher,
    SemanticScholarSearcher,
)

from app.services.paper_discovery.enrichers import (
    CrossrefEnricher,
    UnpaywallEnricher,
)

from app.services.paper_discovery.rankers import (
    GptRanker,
    LexicalRanker,
    SemanticRanker,
    SimpleRanker,
)

from dataclasses import dataclass, field


@dataclass
class SourceStats:
    """Per-source statistics from a discovery run."""
    source: str
    count: int = 0
    status: str = "pending"  # pending, success, timeout, rate_limited, error
    error: Optional[str] = None
    elapsed_ms: int = 0  # milliseconds


@dataclass
class DiscoveryResult:
    """Result of a discovery run including papers and per-source stats."""
    papers: List[DiscoveredPaper] = field(default_factory=list)
    source_stats: List[SourceStats] = field(default_factory=list)

class SearchOrchestrator:
    """Orchestrates the paper discovery process"""
    
    def __init__(
        self,
        searchers: List[PaperSearcher],
        enrichers: List[PaperEnricher],
        ranker: PaperRanker,
        config: DiscoveryConfig
    ):
        self.searchers = searchers
        self.enrichers = enrichers
        self.ranker = ranker
        self.config = config
    
    async def discover_papers(
        self,
        query: str,
        max_results: int = 20,
        target_text: Optional[str] = None,
        target_keywords: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        *,
        fast_mode: bool = False,
        core_terms: Optional[Set[str]] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        open_access_only: bool = False,
        query_intent: Optional[QueryIntent] = None,
        progress_callback: Optional[Callable[..., Any]] = None,
    ) -> DiscoveryResult:
        """Orchestrate paper discovery and return results with per-source stats."""
        search_start_time = time.time()
        logger.info(f"[Search] START query='{query}' | max_results={max_results} | sources={sources} | fast_mode={fast_mode} | core_terms={core_terms or 'none'}")

        async def _notify(event: Dict[str, Any]) -> None:
            """Fire progress callback if provided."""
            if progress_callback is not None:
                try:
                    result = progress_callback(event)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception:
                    pass  # Never let callback errors break the pipeline

        active_searchers = self.searchers
        if sources is not None and len(sources) > 0:
            wanted = {s.lower() for s in sources}
            logger.info(f"Filtering searchers: requested {wanted}, available {[s.get_source_name().lower() for s in self.searchers]}")
            filtered = [searcher for searcher in self.searchers if searcher.get_source_name().lower() in wanted]
            if filtered:
                active_searchers = filtered
                logger.info(f"Using {len(filtered)} filtered searchers: {[s.get_source_name() for s in filtered]}")
            else:
                logger.warning("No matching searchers for requested sources %s; using defaults", sources)
        else:
            logger.info(f"Using all {len(active_searchers)} searchers: {[s.get_source_name() for s in active_searchers]}")

        if fast_mode:
            priority_order = {
                'semantic_scholar': 0,
                'openalex': 1,
                'arxiv': 2,
                'crossref': 3,
                'pubmed': 4,
                'sciencedirect': 5,
                'core': 6,
                'europe_pmc': 7,
            }
            active_searchers = sorted(
                active_searchers,
                key=lambda s: priority_order.get(s.get_source_name(), len(priority_order))
            )
        # Initialize per-source stats tracking
        source_stats_map: Dict[str, SourceStats] = {
            s.get_source_name(): SourceStats(source=s.get_source_name(), status="pending")
            for s in active_searchers
        }

        # Phase 1: Concurrent search with stats tracking
        sem = asyncio.Semaphore(self.config.max_concurrent_searches)

        async def limited_search(searcher: PaperSearcher) -> tuple[str, List[DiscoveredPaper], str, Optional[str], int]:
            """Returns (source_name, papers, status, error, elapsed_ms)"""
            source_name = searcher.get_source_name()
            source_start = time.time()
            async with sem:
                timeout = self.config.search_timeout
                if fast_mode:
                    if max_results <= 5:
                        timeout = min(timeout, 8.0)  # Quick timeout for small searches
                    else:
                        timeout = min(timeout, 15.0)  # Moderate timeout for larger searches
                try:
                    # Pass native filters only to searchers that support them.
                    filter_kwargs: Dict[str, Any] = {}
                    try:
                        sig = inspect.signature(searcher.search)
                        params = sig.parameters
                        accepts_kwargs = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values())
                        if accepts_kwargs or "year_from" in params:
                            filter_kwargs["year_from"] = year_from
                        if accepts_kwargs or "year_to" in params:
                            filter_kwargs["year_to"] = year_to
                        if accepts_kwargs or "open_access_only" in params:
                            filter_kwargs["open_access_only"] = open_access_only
                    except Exception:
                        filter_kwargs = {}

                    papers = await asyncio.wait_for(
                        searcher.search(query, max_results, **filter_kwargs),
                        timeout=timeout
                    )
                    elapsed_ms = int((time.time() - source_start) * 1000)
                    return (source_name, papers, "success", None, elapsed_ms)
                except asyncio.TimeoutError:
                    elapsed_ms = int((time.time() - source_start) * 1000)
                    logger.warning(f"{source_name} timed out after {elapsed_ms}ms")
                    return (source_name, [], "timeout", "Request timed out", elapsed_ms)
                except RateLimitError as e:
                    elapsed_ms = int((time.time() - source_start) * 1000)
                    logger.warning(f"{source_name} rate limited after {elapsed_ms}ms: {e}")
                    return (source_name, [], "rate_limited", "API rate limited", elapsed_ms)
                except Exception as e:  # pragma: no cover - network variability
                    elapsed_ms = int((time.time() - source_start) * 1000)
                    error_msg = str(e)[:100]
                    logger.error(f"{source_name} failed after {elapsed_ms}ms: {e}")
                    return (source_name, [], "error", error_msg, elapsed_ms)

        await _notify({"type": "phase", "phase": "searching", "message": "Searching academic databases..."})

        tasks = [asyncio.create_task(limited_search(s)) for s in active_searchers]

        # Flatten and deduplicate results as they arrive
        # Keep track of papers by key, preferring papers with more complete metadata
        papers_by_key: Dict[str, DiscoveredPaper] = {}
        sources_with_papers = 0
        collection_start = time.monotonic()

        def _paper_completeness_score(p: DiscoveredPaper) -> int:
            """Score paper by metadata completeness. Higher = better."""
            score = 0
            if p.doi:
                score += 10  # DOI is very valuable
            if p.pdf_url:
                score += 5   # PDF URL is valuable
            if p.abstract and len(p.abstract) > 50:
                score += 3   # Good abstract
            if p.year:
                score += 1
            if p.authors and len(p.authors) > 0:
                score += 1
            if p.is_open_access:
                score += 2
            return score

        try:
            for fut in asyncio.as_completed(tasks):
                try:
                    source_name, papers, status, error, elapsed_ms = await fut
                    # Update source stats
                    if source_name in source_stats_map:
                        source_stats_map[source_name].count = len(papers)
                        source_stats_map[source_name].status = status
                        source_stats_map[source_name].error = error
                        source_stats_map[source_name].elapsed_ms = elapsed_ms
                    await _notify({
                        "type": "source_complete",
                        "source": source_name,
                        "status": status,
                        "count": len(papers) if isinstance(papers, list) else 0,
                        "elapsed_ms": elapsed_ms,
                    })
                except asyncio.CancelledError:
                    continue
                except Exception as exc:  # pragma: no cover - defensive
                    logger.error("Discovery task failed: %s", exc)
                    papers = []

                # Fix #8: Only count sources that actually returned papers
                if isinstance(papers, list) and len(papers) > 0:
                    sources_with_papers += 1
                    for paper in papers:
                        key = paper.get_unique_key()
                        if key not in papers_by_key:
                            papers_by_key[key] = paper
                        else:
                            # Keep the paper with more complete metadata
                            existing = papers_by_key[key]
                            if _paper_completeness_score(paper) > _paper_completeness_score(existing):
                                papers_by_key[key] = paper
                                logger.debug(
                                    "Replaced duplicate paper '%s' from %s with version from %s (better metadata)",
                                    paper.title[:50], existing.source, paper.source
                                )

                # Fix #1: Early exit requires >=3 sources with papers, enough results,
                # and at least 3s elapsed to give slower diverse sources time to respond
                elapsed = time.monotonic() - collection_start
                if (fast_mode
                        and sources_with_papers >= 3
                        and len(papers_by_key) >= max_results
                        and elapsed >= 3.0):
                    logger.info(
                        "Early exit: %d papers from %d sources in %.1fs, needed %d",
                        len(papers_by_key), sources_with_papers, elapsed, max_results,
                    )
                    break
        finally:
            # Collect results from any tasks that completed during the gather
            remaining = await asyncio.gather(*tasks, return_exceptions=True)
            for result in remaining:
                if isinstance(result, Exception) or not isinstance(result, tuple):
                    continue
                source_name, papers, status, error, elapsed_ms = result
                if source_name in source_stats_map and source_stats_map[source_name].status == "pending":
                    source_stats_map[source_name].count = len(papers)
                    source_stats_map[source_name].status = status
                    source_stats_map[source_name].error = error
                    source_stats_map[source_name].elapsed_ms = elapsed_ms
                if isinstance(papers, list):
                    for paper in papers:
                        key = paper.get_unique_key()
                        if key not in papers_by_key:
                            papers_by_key[key] = paper

        # Phase 1.5: Supplementary searches using query-understanding search_terms.
        # These catch papers indexed under variant terms (e.g., "CharacterBERT" vs "Character BERT").
        if query_intent and query_intent.search_terms:
            fast_sources = [s for s in active_searchers
                            if s.get_source_name() in ('semantic_scholar', 'openalex', 'arxiv')]
            pre_count = len(papers_by_key)
            supp_tasks = []
            for term in query_intent.search_terms[:2]:
                for searcher in fast_sources:
                    supp_tasks.append(
                        asyncio.wait_for(searcher.search(term, 10), timeout=3.0)
                    )
            supp_results = await asyncio.gather(*supp_tasks, return_exceptions=True)
            for res in supp_results:
                if isinstance(res, Exception) or not isinstance(res, list):
                    continue
                for paper in res:
                    key = paper.get_unique_key()
                    if key not in papers_by_key:
                        papers_by_key[key] = paper
            if len(papers_by_key) > pre_count:
                logger.info(
                    "[Search] Supplementary search_terms added %d papers (total %d)",
                    len(papers_by_key) - pre_count, len(papers_by_key),
                )

        # Fix #7: Secondary title-based dedup to catch cross-key duplicates
        # (e.g., arXiv paper with title-hash key + CrossRef paper with DOI key)
        seen_titles: Dict[str, int] = {}
        deduped: List[DiscoveredPaper] = []
        for paper in papers_by_key.values():
            norm_title = _normalize_title(paper.title)
            if not norm_title:
                deduped.append(paper)
                continue
            title_hash = hashlib.md5(norm_title.encode()).hexdigest()
            if title_hash in seen_titles:
                idx = seen_titles[title_hash]
                if _paper_completeness_score(paper) > _paper_completeness_score(deduped[idx]):
                    logger.debug(
                        "Title-dedup: replaced '%s' from %s with %s (better metadata)",
                        paper.title[:50], deduped[idx].source, paper.source,
                    )
                    deduped[idx] = paper
            else:
                seen_titles[title_hash] = len(deduped)
                deduped.append(paper)

        all_papers = deduped

        # Phase 2: Enrichment
        await _notify({"type": "phase", "phase": "enriching", "message": "Enriching paper metadata..."})
        enrichment_tasks = [
            enricher.enrich(all_papers) for enricher in self.enrichers
        ]
        await asyncio.gather(*enrichment_tasks, return_exceptions=True)

        # Phase 2.5: Deterministic hard filters (provider-agnostic safety net).
        # This prevents recency/OA leaks when any upstream source ignores filters.
        filtered_papers, removed_by_year, removed_by_oa = self._apply_hard_filters(
            all_papers,
            year_from=year_from,
            year_to=year_to,
            open_access_only=open_access_only,
        )
        if removed_by_year or removed_by_oa:
            logger.info(
                "[Search] Hard filters applied | removed_by_year=%s removed_by_oa=%s kept=%s/%s",
                removed_by_year,
                removed_by_oa,
                len(filtered_papers),
                len(all_papers),
            )

        # Phase 3: Ranking
        await _notify({"type": "phase", "phase": "ranking", "message": "AI-ranking papers by relevance..."})
        # (pass core_terms for boost + semantic context from query understanding)
        # Use interpreted_query as the ranking query when available — it disambiguates
        # vague queries (e.g. "Arabic check processing" → "Arabic bank cheque recognition")
        ranking_query = query
        rank_kwargs: Dict[str, Any] = {
            "target_text": target_text,
            "target_keywords": target_keywords,
            "core_terms": core_terms or set(),
        }
        if query_intent and query_intent.interpreted_query and query_intent.interpreted_query != query:
            ranking_query = query_intent.interpreted_query
            rank_kwargs["semantic_context"] = query_intent.interpreted_query
        ranked_papers = await self.ranker.rank(
            filtered_papers,
            ranking_query,
            **rank_kwargs,
        )

        # Phase 3.1: Concept overlap gate — penalize papers matching too few query concepts
        if core_terms and len(core_terms) >= 3:
            for paper in ranked_papers:
                text = f"{paper.title} {paper.abstract or ''}".lower()
                hits = sum(1 for t in core_terms if t in text)
                ratio = hits / len(core_terms)
                if ratio < 0.3:
                    paper.relevance_score *= max(0.1, ratio)
            ranked_papers.sort(key=lambda p: p.relevance_score, reverse=True)

        # Phase 3.2: Relevance floor — remove papers scored below threshold
        MIN_RELEVANCE = 0.25
        pre_floor_count = len(ranked_papers)
        ranked_papers = [p for p in ranked_papers if p.relevance_score >= MIN_RELEVANCE]
        if len(ranked_papers) < pre_floor_count:
            logger.info(
                "[Search] Relevance floor removed %d/%d papers below %.2f",
                pre_floor_count - len(ranked_papers), pre_floor_count, MIN_RELEVANCE,
            )
        # Always return at least 5 results even if scores are low
        if len(ranked_papers) < 5 and pre_floor_count >= 5:
            ranked_papers = sorted(filtered_papers, key=lambda p: p.relevance_score, reverse=True)[:5]

        # Phase 3.5: Source-diversity reranking
        # Prevent any single source from dominating the final results
        ranked_papers = self._apply_source_diversity(ranked_papers, max_results)

        # Telemetry: comprehensive search summary
        search_elapsed = time.time() - search_start_time
        source_counts = {s.source: s.count for s in source_stats_map.values()}
        source_times = {s.source: s.elapsed_ms for s in source_stats_map.values()}
        rate_limited = [s.source for s in source_stats_map.values() if s.status == "rate_limited"]
        degraded = [s.source for s in source_stats_map.values() if s.status in ("timeout", "rate_limited", "error")]

        logger.info(
            f"[Search] COMPLETE query='{query}' | "
            f"results={len(ranked_papers[:max_results])}/{len(filtered_papers)}/{len(all_papers)} (returned/filtered/deduped) | "
            f"counts={source_counts} | "
            f"times_ms={source_times} | "
            f"rate_limited={rate_limited or 'none'} | "
            f"degraded={degraded or 'none'} | "
            f"total_elapsed={search_elapsed:.2f}s"
        )

        return DiscoveryResult(
            papers=ranked_papers[:max_results],
            source_stats=list(source_stats_map.values())
        )

    def _apply_hard_filters(
        self,
        papers: List[DiscoveredPaper],
        *,
        year_from: Optional[int],
        year_to: Optional[int],
        open_access_only: bool,
    ) -> tuple[List[DiscoveredPaper], int, int]:
        """Enforce year/OA constraints after retrieval as a deterministic fallback."""
        if not papers:
            return ([], 0, 0)

        start_year = year_from
        end_year = year_to
        if start_year is not None and end_year is not None and start_year > end_year:
            start_year, end_year = end_year, start_year

        filtered: List[DiscoveredPaper] = []
        removed_by_year = 0
        removed_by_oa = 0

        for paper in papers:
            if start_year is not None or end_year is not None:
                paper_year = getattr(paper, "year", None)
                if paper_year is None:
                    removed_by_year += 1
                    continue
                try:
                    year_int = int(paper_year)
                except (TypeError, ValueError):
                    removed_by_year += 1
                    continue
                if start_year is not None and year_int < start_year:
                    removed_by_year += 1
                    continue
                if end_year is not None and year_int > end_year:
                    removed_by_year += 1
                    continue

            if open_access_only:
                has_oa_access = bool(
                    getattr(paper, "is_open_access", False)
                    or getattr(paper, "pdf_url", None)
                    or getattr(paper, "open_access_url", None)
                )
                if not has_oa_access:
                    removed_by_oa += 1
                    continue

            filtered.append(paper)

        return (filtered, removed_by_year, removed_by_oa)

    @staticmethod
    def _apply_source_diversity(
        papers: List[DiscoveredPaper], max_results: int
    ) -> List[DiscoveredPaper]:
        """Prevent any single source from dominating the top results.

        Caps each source at 40% of max_results. Papers bumped out are appended
        at the end so total count is preserved.
        """
        if len(papers) <= 1:
            return papers

        max_per_source = max(2, int(max_results * 0.4))
        source_counts: Dict[str, int] = {}
        result: List[DiscoveredPaper] = []
        deferred: List[DiscoveredPaper] = []

        for paper in papers:
            count = source_counts.get(paper.source, 0)
            if count < max_per_source:
                result.append(paper)
                source_counts[paper.source] = count + 1
            else:
                deferred.append(paper)

        # Fill remaining slots with deferred papers
        return result + deferred


# ============= Main Service Factory =============
class PaperDiscoveryServiceFactory:
    """Factory for creating the discovery service"""
    
    @staticmethod
    async def create(
        config: Optional[DiscoveryConfig] = None,
        openai_api_key: Optional[str] = None,
        semantic_scholar_api_key: Optional[str] = None,
        unpaywall_email: Optional[str] = None,
        ncbi_email: Optional[str] = None,
    ) -> 'PaperDiscoveryService':
        """Create a configured discovery service"""
        
        if config is None:
            config = DiscoveryConfig()
        
        if config.ncbi_email is None and ncbi_email is not None:
            config.ncbi_email = ncbi_email

        # Create HTTP session
        timeout = aiohttp.ClientTimeout(total=120, connect=10)
        connector = aiohttp.TCPConnector(limit=50, limit_per_host=10)
        session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        
        # Create searchers
        resolved_ncbi_email = (
            config.ncbi_email
            or ncbi_email
            or os.getenv('NCBI_EMAIL')
            or unpaywall_email
            or os.getenv('UNPAYWALL_EMAIL')
        )
        sciencedirect_api_key = (
            config.sciencedirect_api_key
            or os.getenv('SCIENCEDIRECT_API_KEY')
        )
        if config.sciencedirect_api_key is None and sciencedirect_api_key is not None:
            config.sciencedirect_api_key = sciencedirect_api_key

        # Get CORE API key from environment
        core_api_key = os.getenv("CORE_API_KEY")

        searchers = [
            ArxivSearcher(session, config),
            SemanticScholarSearcher(session, config, semantic_scholar_api_key),
            CrossrefSearcher(session, config),
            PubMedSearcher(session, config, email=resolved_ncbi_email),
            ScienceDirectSearcher(session, config, api_key=sciencedirect_api_key),
            OpenAlexSearcher(session, config),
            CoreSearcher(session, config, api_key=core_api_key),
            EuropePmcSearcher(session, config),
        ]
        
        # Purged advanced ranking flags: no-op

        # Create enrichers
        enrichers: List[PaperEnricher] = [
            CrossrefEnricher(session, config),
        ]
        if unpaywall_email:
            enrichers.append(UnpaywallEnricher(session, config, unpaywall_email))
        
        # Create ranker based on environment configuration
        # Priority: SemanticRanker (if enabled) > GptRanker (if API key) > SimpleRanker
        service_ranker: PaperRanker
        use_semantic = os.getenv("USE_SEMANTIC_RANKER", "").lower() in ("true", "1", "yes")
        if use_semantic:
            logger.info("[Discovery] Using SemanticRanker (bi-encoder + cross-encoder)")
            service_ranker = SemanticRanker(config)
        elif settings.OPENROUTER_API_KEY:
            service_ranker = GptRanker(config)
        else:
            service_ranker = SimpleRanker(config)

        # Create orchestrator
        orchestrator = SearchOrchestrator(searchers, enrichers, service_ranker, config)
        
        return PaperDiscoveryService(
            orchestrator=orchestrator,
            session=session,
            config=config,
            ncbi_email=resolved_ncbi_email,
            unpaywall_email=unpaywall_email,
            owns_session=True
        )


class PaperDiscoveryService:
    """Main paper discovery service with clean architecture"""
    
    def __init__(
        self,
        orchestrator: Optional[SearchOrchestrator] = None,
        session: Optional[aiohttp.ClientSession] = None,
        config: Optional[DiscoveryConfig] = None,
        *,
        openai_api_key: Optional[str] = None,
        semantic_scholar_api_key: Optional[str] = None,
        unpaywall_email: Optional[str] = None,
        ncbi_email: Optional[str] = None,
        owns_session: Optional[bool] = None,
    ):
        """Initialize discovery service.

        Legacy call sites still instantiate the service without arguments. To maintain
        backwards compatibility we lazily construct the orchestrator, session, and
        enhancer when they are not provided. Newer code paths may still supply
        pre-built components (e.g., via the factory) without penalty.
        """

        self.config = config or DiscoveryConfig()
        self.unpaywall_email = unpaywall_email or os.getenv('UNPAYWALL_EMAIL')
        self._unpaywall_cache: Dict[str, Optional[str]] = {}

        # HTTP session management
        self._owns_session = owns_session if owns_session is not None else session is None
        if session is None:
            timeout = aiohttp.ClientTimeout(total=120, connect=10)
            connector = aiohttp.TCPConnector(limit=50, limit_per_host=10)
            session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            self._owns_session = True
        self.session = session

        resolved_ncbi_email = (
            ncbi_email
            or self.config.ncbi_email
            or os.getenv('NCBI_EMAIL')
            or unpaywall_email
            or os.getenv('UNPAYWALL_EMAIL')
        )
        if self.config.ncbi_email is None and resolved_ncbi_email is not None:
            self.config.ncbi_email = resolved_ncbi_email

        sciencedirect_api_key = (
            self.config.sciencedirect_api_key
            or os.getenv('SCIENCEDIRECT_API_KEY')
        )
        if self.config.sciencedirect_api_key is None and sciencedirect_api_key is not None:
            self.config.sciencedirect_api_key = sciencedirect_api_key

        # Get CORE API key
        core_api_key = os.getenv("CORE_API_KEY")

        # Orchestrator with default searchers/enrichers/ranker
        if orchestrator is None:
            searchers: List[PaperSearcher] = [
                ArxivSearcher(self.session, self.config),
                SemanticScholarSearcher(
                    self.session,
                    self.config,
                    api_key=semantic_scholar_api_key or os.getenv("SEMANTIC_SCHOLAR_API_KEY"),
                ),
                # Ensure Crossref is available when filtering to sources=['crossref']
                CrossrefSearcher(self.session, self.config),
                PubMedSearcher(self.session, self.config, email=resolved_ncbi_email),
                ScienceDirectSearcher(self.session, self.config, api_key=sciencedirect_api_key),
                OpenAlexSearcher(self.session, self.config),
                CoreSearcher(self.session, self.config, api_key=core_api_key),
                EuropePmcSearcher(self.session, self.config),
            ]

            enrichers: List[PaperEnricher] = [
                CrossrefEnricher(self.session, self.config),
            ]
            email = unpaywall_email or os.getenv("UNPAYWALL_EMAIL")
            if email:
                enrichers.append(UnpaywallEnricher(self.session, self.config, email))

            # Create ranker per env
            # Priority: SemanticRanker (if enabled) > GptRanker (if API key) > SimpleRanker
            ranker_for_env: PaperRanker
            use_semantic = os.getenv("USE_SEMANTIC_RANKER", "").lower() in ("true", "1", "yes")
            if use_semantic:
                ranker_for_env = SemanticRanker(self.config)
            elif settings.OPENROUTER_API_KEY:
                ranker_for_env = GptRanker(self.config)
            else:
                ranker_for_env = SimpleRanker(self.config)
            orchestrator = SearchOrchestrator(searchers, enrichers, ranker_for_env, self.config)
        self.orchestrator = orchestrator

        self._metrics: Dict[str, Any] = {}
    
    async def discover_papers(
        self,
        query: str,
        max_results: int = 20,
        target_text: Optional[str] = None,
        target_keywords: Optional[List[str]] = None,
        sources: Optional[List[str]] = None,
        debug: bool = False,
        fast_mode: bool = False,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        open_access_only: bool = False,
        progress_callback: Optional[Callable[..., Any]] = None,
    ) -> DiscoveryResult:
        """Main discovery method with clean orchestration"""

        start_time = time.time()
        timings = {}

        logger.info(
            "PaperDiscoveryService.discover_papers called with query='%s', sources=%s, "
            "year_from=%s, year_to=%s, open_access_only=%s",
            query,
            sources,
            year_from,
            year_to,
            open_access_only,
        )

        try:
            # Extract core terms from original query BEFORE enhancement
            core_terms = extract_core_terms(query)
            logger.info(f"[CoreTerms] Extracted from '{query}': {core_terms}")

            # Fire query understanding in parallel with source searches.
            # The LLM interprets compound academic concepts for ranking
            # (e.g. "Arabic character BERT" → semantic context about CharacterBERT).
            # We always search with the ORIGINAL query because LLM rewrites can
            # introduce compound terms (e.g. "CharacterBERT") that don't match
            # source indices where papers use separate words ("Character BERT").
            intent_task = asyncio.create_task(understand_query(query))

            # Run discovery
            effective_target_text = target_text
            phase_start = time.time()

            # Await query intent (used for ranking context + supplementary searches)
            intent = await intent_task
            if intent.search_terms:
                logger.info(f"[QueryIntent] Understood '{query}' → search_terms={intent.search_terms}")
            else:
                logger.info(f"[QueryIntent] No rewrite for query: '{query}'")

            result = await self.orchestrator.discover_papers(
                query,
                max_results,
                target_text=effective_target_text,
                target_keywords=target_keywords,
                sources=sources,
                fast_mode=fast_mode,
                core_terms=core_terms,
                year_from=year_from,
                year_to=year_to,
                open_access_only=open_access_only,
                query_intent=intent,
                progress_callback=progress_callback,
            )
            papers = result.papers
            if fast_mode:
                logger.info("[PDF] Skipping PDF augmentation in fast mode (%d papers)", len(papers))
            else:
                pdf_start = time.time()
                await self._augment_pdf_links(papers, fast_mode=fast_mode)
                logger.info("[PDF] Augmentation took %.1fs for %d papers", time.time() - pdf_start, len(papers))
            for paper in papers:
                if getattr(paper, 'pdf_url', None):
                    paper.is_open_access = True
                else:
                    paper.is_open_access = False
            timings['discovery'] = time.time() - phase_start

            timings['total'] = time.time() - start_time

            # Store metrics
            self._metrics = {
                'timings': timings,
                'papers_found': len(papers),
                'timestamp': datetime.utcnow().isoformat()
            }

            # Telemetry: comprehensive discovery summary
            source_summary = {s.source: f"{s.count}({s.status})" for s in result.source_stats}
            rate_limit_pct = (
                sum(1 for s in result.source_stats if s.status == "rate_limited") / len(result.source_stats) * 100
                if result.source_stats else 0
            )
            # Calculate core term presence in results
            core_term_hits = 0
            if core_terms and papers:
                for p in papers:
                    title_lower = (p.title or '').lower()
                    abstract_lower = (p.abstract or '').lower()
                    if any(term in title_lower or term in abstract_lower for term in core_terms):
                        core_term_hits += 1
                core_term_pct = (core_term_hits / len(papers)) * 100
            else:
                core_term_pct = 0.0

            logger.info(
                f"[Discovery] query='{query}' | "
                f"core_terms={core_terms} | "
                f"papers={len(papers)} | "
                f"core_term_presence={core_term_pct:.1f}% ({core_term_hits}/{len(papers)}) | "
                f"sources={source_summary} | "
                f"rate_limit_pct={rate_limit_pct:.1f}% | "
                f"timings={{enhance={timings.get('query_enhancement', 0):.2f}s, search={timings.get('discovery', 0):.2f}s, total={timings['total']:.2f}s}}"
            )

            if debug:
                logger.info(f"Discovery metrics: {self._metrics}")

            return result

        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return DiscoveryResult(papers=[], source_stats=[])
    
    async def close(self):
        """Clean up resources"""
        if self._owns_session and not self.session.closed:
            await self.session.close()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _augment_pdf_links(self, papers: List[DiscoveredPaper], *, fast_mode: bool = False) -> None:
        """Best-effort augmentation to ensure open-access papers expose direct PDF URLs."""
        if not papers:
            return

        sem = asyncio.Semaphore(self.config.max_concurrent_pdf_checks)

        if fast_mode:
            fast_verify_tasks = [
                self._verify_existing_pdf_link(paper, sem)
                for paper in papers
                if paper.source == PaperSource.OPENALEX.value and paper.pdf_url
            ]
            if fast_verify_tasks:
                await asyncio.gather(*fast_verify_tasks, return_exceptions=True)
            return

        verify_tasks = [
            self._verify_existing_pdf_link(paper, sem)
            for paper in papers
            if paper.pdf_url
        ]
        if verify_tasks:
            await asyncio.gather(*verify_tasks, return_exceptions=True)

        tasks = []
        for paper in papers:
            if paper.pdf_url:
                continue
            candidates = self._candidate_pdf_urls(paper)
            if not candidates:
                continue
            tasks.append(self._resolve_pdf_for_paper(paper, candidates, sem))

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _verify_existing_pdf_link(
        self,
        paper: DiscoveredPaper,
        sem: asyncio.Semaphore,
    ) -> None:
        original = getattr(paper, 'pdf_url', None)
        if not original:
            return

        resolved = await self._check_pdf_candidate(original, sem)
        if resolved:
            paper.pdf_url = resolved
            if not getattr(paper, 'open_access_url', None):
                paper.open_access_url = resolved
            paper.is_open_access = True
            return

        if getattr(paper, 'pdf_url', None) == original:
            paper.pdf_url = None
        if paper.source == PaperSource.OPENALEX.value:
            try:
                if paper.open_access_url and paper.open_access_url == original:
                    paper.open_access_url = None
                elif paper.open_access_url and paper.open_access_url.lower().endswith('.pdf'):
                    paper.open_access_url = None
            except Exception:
                paper.open_access_url = None
        paper.is_open_access = False

    def _candidate_pdf_urls(self, paper: DiscoveredPaper) -> List[str]:
        candidates: List[str] = []

        def add(url: Optional[str]) -> None:
            if url and url not in candidates:
                candidates.append(url)

        host = ''
        if paper.url:
            try:
                host = urlparse(paper.url).netloc.lower()
            except Exception:
                host = ''

        allow_hosts = {
            'arxiv.org',
            'www.arxiv.org',
            'biorxiv.org',
            'www.biorxiv.org',
            'medrxiv.org',
            'www.medrxiv.org',
            'ncbi.nlm.nih.gov',
            'pubmed.ncbi.nlm.nih.gov',
            'openaccess.thecvf.com',
            'proceedings.mlr.press',
            'cran.r-project.org',
            'papers.ssrn.com',
            'hdl.handle.net',
            'boa.unimib.it',
            'dl.acm.org',
            'semanticscholar.org',
            'www.semanticscholar.org',
        }

        if not paper.is_open_access and not paper.open_access_url and host not in allow_hosts:
            return candidates

        add(paper.open_access_url)
        if paper.url and (host in allow_hosts):
            add(paper.url)

        if host == 'papers.ssrn.com' and paper.url:
            parsed = urlparse(paper.url)
            params = parse_qs(parsed.query.lower())
            abstract_id = (
                params.get('abstract_id')
                or params.get('abstractid')
                or params.get('abstractid[]')
            )
            if abstract_id:
                aid = abstract_id[0]
                delivery = f"https://papers.ssrn.com/sol3/Delivery.cfm?abstractid={aid}&type=2"
                add(delivery)

        if host == 'ieeexplore.ieee.org' and paper.url:
            try:
                path = urlparse(paper.url).path
                match = re.search(r'/document/(\d+)', path)
                if match:
                    arnumber = match.group(1)
                    stamp_url = f"https://ieeexplore.ieee.org/stamp/stamp.jsp?tp=&arnumber={arnumber}"
                    add(stamp_url)
            except Exception:
                pass

        if host.endswith('dl.acm.org') and paper.url:
            try:
                if '/doi/' in paper.url:
                    add(paper.url.replace('/doi/', '/doi/pdf/'))
            except Exception:
                pass

        if host.endswith('semanticscholar.org') and paper.url:
            try:
                if '/paper/' in paper.url and '/pdf' not in paper.url:
                    add(paper.url.rstrip('/') + '/pdf')
            except Exception:
                pass

        if paper.doi:
            host = ''
            if paper.url:
                host = urlparse(paper.url).netloc.lower()
            if 'arxiv.org' in host or 'doi.org' in (urlparse(additional).netloc if (additional := paper.open_access_url) else ''):
                add(f"https://doi.org/{paper.doi}")

        # Special-case heuristics per source
        if paper.source == PaperSource.ARXIV.value and paper.url:
            try:
                alt = paper.url.replace('/abs/', '/pdf/')
                if not alt.endswith('.pdf'):
                    alt = f"{alt}.pdf"
                add(alt)
            except Exception:
                pass

        return candidates

    async def _resolve_pdf_for_paper(
        self,
        paper: DiscoveredPaper,
        candidates: List[str],
        sem: asyncio.Semaphore,
    ) -> None:
        if paper.pdf_url:
            return

        if paper.doi and self.unpaywall_email:
            pdf_from_unpaywall = await self._fetch_unpaywall_pdf(paper.doi, sem)
            if pdf_from_unpaywall:
                paper.pdf_url = pdf_from_unpaywall
                if not paper.open_access_url:
                    paper.open_access_url = pdf_from_unpaywall
                return

        for candidate in candidates:
            pdf_url = await self._check_pdf_candidate(candidate, sem)
            if pdf_url:
                paper.pdf_url = pdf_url
                if not paper.open_access_url:
                    paper.open_access_url = pdf_url
                paper.is_open_access = True
                return
            try:
                parsed = urlparse(candidate)
                host = (parsed.netloc or '').lower()
                path = (parsed.path or '').lower()
            except Exception:
                host = ''
                path = ''
            if host.endswith('dl.acm.org') and '/doi/pdf/' in path:
                paper.pdf_url = candidate
                if not paper.open_access_url:
                    paper.open_access_url = candidate
                paper.is_open_access = True
                return
            if host.endswith('semanticscholar.org') and path.endswith('/pdf'):
                paper.pdf_url = candidate
                if not paper.open_access_url:
                    paper.open_access_url = candidate
                paper.is_open_access = True
                return

        # As a final fallback, scrape the landing/open-access page for embedded PDF links.
        for landing in filter(None, [paper.open_access_url, paper.url]):
            pdf_url = await self._scrape_pdf_from_page(landing, sem)
            if pdf_url:
                paper.pdf_url = pdf_url
                if not paper.open_access_url:
                    paper.open_access_url = pdf_url
                paper.is_open_access = True
                return

    async def _check_pdf_candidate(
        self,
        url: str,
        sem: asyncio.Semaphore,
        depth: int = 0,
    ) -> Optional[str]:
        if depth > 2:
            return None

        timeout = aiohttp.ClientTimeout(total=self.config.pdf_check_timeout)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36'
        }

        parsed_url = urlparse(url)
        host = (parsed_url.netloc or '').lower()
        path = (parsed_url.path or '').lower()
        is_nature_pdf = host.endswith('nature.com') and path.endswith('.pdf')

        try:
            async with sem:
                async with self.session.head(url, allow_redirects=True, timeout=timeout, headers=headers) as resp:
                    if resp.status < 400:
                        content_type = (resp.headers.get('content-type') or '').lower()
                        if 'pdf' in content_type:
                            return str(resp.url)
        except Exception:
            pass

        try:
            async with sem:
                range_headers = {
                    **headers,
                    'Range': 'bytes=0-2048',
                    'Accept': 'application/pdf,application/octet-stream,text/html;q=0.9,*/*;q=0.8',
                }
                async with self.session.get(url, allow_redirects=True, timeout=timeout, headers=range_headers) as resp:
                    if resp.status >= 400:
                        return None
                    content_type = (resp.headers.get('content-type') or '').lower()
                    disposition = (resp.headers.get('content-disposition') or '').lower()
                    if 'pdf' in disposition:
                        return str(resp.url)
                    if 'pdf' in content_type:
                        return str(resp.url)

                    if 'html' in content_type:
                        if is_nature_pdf:
                            return None
                        snippet_bytes = await resp.content.read(120000)
                        snippet = snippet_bytes.decode('utf-8', errors='ignore')
                        if snippet.lstrip().startswith('%PDF'):
                            return str(resp.url)
                        for link in self._extract_pdf_links(snippet, str(resp.url)):
                            resolved = await self._check_pdf_candidate(link, sem, depth + 1)
                            if resolved:
                                return resolved
                    else:
                        # Unknown content type; check magic number for PDF
                        snippet_bytes = await resp.content.read(8)
                        if snippet_bytes.startswith(b'%PDF'):
                            return str(resp.url)
        except Exception:
            pass

        return None

    async def _scrape_pdf_from_page(
        self,
        url: str,
        sem: asyncio.Semaphore,
    ) -> Optional[str]:
        """Fetch the HTML for a landing page and extract the first PDF link."""
        timeout = aiohttp.ClientTimeout(total=max(self.config.pdf_check_timeout * 2, 10))
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        }

        try:
            async with sem:
                async with self.session.get(url, allow_redirects=True, timeout=timeout, headers=headers) as resp:
                    if resp.status >= 400:
                        return None
                    html = await resp.text()
                    links = self._extract_pdf_links(html, str(resp.url))
        except Exception:
            return None

        for link in links[:6]:
            try:
                verified = await self._check_pdf_candidate(link, sem, depth=1)
            except Exception:
                verified = None
            if verified:
                return verified
            # If verification fails but link looks like a PDF, return it optimistically.
            lower = link.lower()
            if lower.endswith('.pdf'):
                try:
                    host = urlparse(link).netloc.lower()
                except Exception:
                    host = ''
                if host.endswith('nature.com'):
                    continue
                return link

        return None

    def _extract_pdf_links(self, html: str, base_url: str) -> List[str]:
        matches = re.findall(r'href=["\']([^"\']+\.pdf(?:\?[^"\']*)?)', html, flags=re.IGNORECASE)
        meta_matches = re.findall(r'content=["\']([^"\']+\.pdf(?:\?[^"\']*)?)["\']', html, flags=re.IGNORECASE)
        citation_meta = re.findall(r'name=["\']citation_pdf_url["\']\s+content=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
        links = matches + meta_matches + citation_meta
        resolved: List[str] = []
        for link in links:
            candidate = urljoin(base_url, link)
            if candidate not in resolved:
                resolved.append(candidate)
        return resolved

    async def _fetch_unpaywall_pdf(
        self,
        doi: str,
        sem: Optional[asyncio.Semaphore] = None,
    ) -> Optional[str]:
        if not self.unpaywall_email:
            return None

        key = doi.strip().lower()
        if not key:
            return None

        if key in self._unpaywall_cache:
            return self._unpaywall_cache[key]

        params = {'email': self.unpaywall_email}
        url = f"https://api.unpaywall.org/v2/{quote(key)}"
        timeout = aiohttp.ClientTimeout(total=max(5.0, self.config.pdf_check_timeout * 2))

        try:
            async with self.session.get(url, params=params, timeout=timeout) as resp:
                if resp.status != 200:
                    self._unpaywall_cache[key] = None
                    return None
                data = await resp.json()
        except Exception:
            self._unpaywall_cache[key] = None
            return None

        best = data.get('best_oa_location') or {}
        candidate = best.get('url_for_pdf') or best.get('url')
        if not candidate:
            self._unpaywall_cache[key] = None
            return None

        candidate = candidate.strip()
        if candidate.lower().endswith('.pdf'):
            try:
                host = urlparse(candidate).netloc.lower()
            except Exception:
                host = ''
            if not host.endswith('nature.com'):
                self._unpaywall_cache[key] = candidate
                return candidate

        if sem is None:
            sem = asyncio.Semaphore(self.config.max_concurrent_pdf_checks)
        resolved = await self._check_pdf_candidate(candidate, sem)
        self._unpaywall_cache[key] = resolved
        return resolved


# ============= Usage Example =============
async def example_usage():
    """Example of how to use the refactored service"""
    
    # Create service using factory
    service = await PaperDiscoveryServiceFactory.create(
        config=DiscoveryConfig(
            max_concurrent_searches=3,
            search_timeout=10.0
        ),
        openai_api_key="your-api-key",
        semantic_scholar_api_key="your-api-key",
        unpaywall_email="your-email@example.com"
    )
    
    async with service:
        papers = await service.discover_papers(
            query="machine learning optimization",
            max_results=20,
            debug=True
        )
        
        for paper in papers[:5]:
            print(f"{paper.title} (Score: {paper.relevance_score:.2f})")
