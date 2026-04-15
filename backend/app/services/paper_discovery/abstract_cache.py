"""Persistent abstract cache and multi-source fetchers.

Academic paper abstracts are immutable once published, so fetching them is a
one-time cost. This module provides:

- `bulk_lookup(dois)` — batch read from the cache table
- `fetch_missing(papers)` — try several free APIs in parallel for papers whose
  abstract is still empty after other enrichers, then write results (including
  negative results) to the cache

Sources tried, in order:
1. Crossref (already tried upstream — we skip if still empty)
2. Elsevier Article Retrieval API (free 10k/week; good for Elsevier DOIs)
3. CORE works API (free 10k/day; green OA aggregator with wide coverage)
4. Semantic Scholar abstract fallback (already tried upstream — skip)

Each source is tried in parallel (bounded). First non-empty wins. We write
*everything* to the cache — even negative ("unavailable") entries — so we don't
retry known-empty DOIs.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional

import aiohttp
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services.paper_discovery.models import DiscoveredPaper

logger = logging.getLogger(__name__)

MIN_ABSTRACT_LEN = 50
MAX_PARALLEL_PER_SOURCE = 6
PER_FETCH_TIMEOUT = 5.0
MAX_ATTEMPTS_BEFORE_GIVEUP = 3


@dataclass
class CachedAbstract:
    doi: str
    abstract: Optional[str]
    source: Optional[str]
    status: str  # 'fresh' | 'unavailable'


# ---------------------------------------------------------------------------
# Cache I/O
# ---------------------------------------------------------------------------

def _normalize_doi(doi: Optional[str]) -> Optional[str]:
    if not doi:
        return None
    d = doi.strip()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        if d.lower().startswith(prefix):
            d = d[len(prefix):]
    return d.lower() or None


def bulk_lookup(db: Session, dois: List[str]) -> Dict[str, CachedAbstract]:
    """Return a dict of {doi_normalized: CachedAbstract} for every hit."""
    clean = [d for d in {_normalize_doi(x) for x in dois} if d]
    if not clean:
        return {}
    rows = db.execute(
        text(
            "SELECT doi, abstract, source, status FROM paper_abstracts "
            "WHERE doi = ANY(:dois)"
        ),
        {"dois": clean},
    ).fetchall()
    return {
        row.doi: CachedAbstract(
            doi=row.doi,
            abstract=row.abstract,
            source=row.source,
            status=row.status,
        )
        for row in rows
    }


def bulk_upsert(db: Session, records: List[CachedAbstract]) -> None:
    """Insert or update cache rows. Increments attempts on conflict."""
    if not records:
        return
    now = datetime.now(timezone.utc)
    for rec in records:
        db.execute(
            text(
                """
                INSERT INTO paper_abstracts (doi, abstract, source, status, attempts, fetched_at)
                VALUES (:doi, :abstract, :source, :status, 1, :fetched_at)
                ON CONFLICT (doi) DO UPDATE SET
                    abstract = COALESCE(EXCLUDED.abstract, paper_abstracts.abstract),
                    source = COALESCE(EXCLUDED.source, paper_abstracts.source),
                    status = EXCLUDED.status,
                    attempts = paper_abstracts.attempts + 1,
                    fetched_at = EXCLUDED.fetched_at
                """
            ),
            {
                "doi": rec.doi,
                "abstract": rec.abstract,
                "source": rec.source,
                "status": rec.status,
                "fetched_at": now,
            },
        )
    db.commit()


# ---------------------------------------------------------------------------
# Fetchers — each returns (abstract, source_label) or (None, None)
# ---------------------------------------------------------------------------

async def _fetch_elsevier(
    session: aiohttp.ClientSession, doi: str, api_key: str
) -> tuple[Optional[str], Optional[str]]:
    """Elsevier Article Retrieval API — free tier, 10k req/week.
    Returns abstract for Elsevier-published articles (DOI prefix typically 10.1016/,
    10.1007/ for some co-published content, etc.). Works for many OA and closed-access
    articles, subject to Elsevier's content availability rules.
    """
    try:
        url = f"https://api.elsevier.com/content/article/doi/{doi}"
        headers = {
            "X-ELS-APIKey": api_key,
            "Accept": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=PER_FETCH_TIMEOUT)
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.json()
        core = data.get("full-text-retrieval-response", {}).get("coredata", {})
        raw = core.get("dc:description") or ""
        if isinstance(raw, list):
            raw = raw[0] if raw else ""
        abstract = re.sub(r'\s+', ' ', str(raw)).strip()
        if len(abstract) >= MIN_ABSTRACT_LEN:
            return abstract, "elsevier"
    except Exception as e:
        logger.debug("Elsevier fetch failed for %s: %s", doi, e)
    return None, None


async def _fetch_core(
    session: aiohttp.ClientSession, doi: str, api_key: str
) -> tuple[Optional[str], Optional[str]]:
    """CORE works API — free 10k/day. Aggregates green OA content."""
    try:
        url = "https://api.core.ac.uk/v3/search/works"
        headers = {"Authorization": f"Bearer {api_key}"}
        payload = {"q": f'doi:"{doi}"', "limit": 1}
        timeout = aiohttp.ClientTimeout(total=PER_FETCH_TIMEOUT)
        async with session.post(url, headers=headers, json=payload, timeout=timeout) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.json()
        results = data.get("results") or []
        if not results:
            return None, None
        raw = results[0].get("abstract") or ""
        abstract = re.sub(r'\s+', ' ', str(raw)).strip()
        if len(abstract) >= MIN_ABSTRACT_LEN:
            return abstract, "core"
    except Exception as e:
        logger.debug("CORE fetch failed for %s: %s", doi, e)
    return None, None


async def _fetch_semantic_scholar(
    session: aiohttp.ClientSession, doi: str, api_key: Optional[str]
) -> tuple[Optional[str], Optional[str]]:
    """Semantic Scholar — sometimes has abstracts when other sources don't.
    Only used as a tertiary fallback because upstream SemanticScholarSearcher
    already returned data from this source; we hit the direct DOI endpoint.
    """
    try:
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}?fields=abstract"
        headers = {}
        if api_key:
            headers["x-api-key"] = api_key
        timeout = aiohttp.ClientTimeout(total=PER_FETCH_TIMEOUT)
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status != 200:
                return None, None
            data = await resp.json()
        raw = data.get("abstract") or ""
        abstract = re.sub(r'\s+', ' ', str(raw)).strip()
        if len(abstract) >= MIN_ABSTRACT_LEN:
            return abstract, "semantic_scholar"
    except Exception as e:
        logger.debug("Semantic Scholar fetch failed for %s: %s", doi, e)
    return None, None


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


async def fetch_one(
    session: aiohttp.ClientSession, doi: str
) -> tuple[Optional[str], Optional[str]]:
    """Try each configured source; return first non-empty result."""
    elsevier_key = os.getenv("SCIENCEDIRECT_API_KEY")  # same key used for ScienceDirect
    core_key = os.getenv("CORE_API_KEY")
    s2_key = os.getenv("SEMANTIC_SCHOLAR_API_KEY")

    tasks = []
    if elsevier_key:
        tasks.append(_fetch_elsevier(session, doi, elsevier_key))
    if core_key:
        tasks.append(_fetch_core(session, doi, core_key))
    tasks.append(_fetch_semantic_scholar(session, doi, s2_key))

    if not tasks:
        return None, None

    # Fire all in parallel, return the first non-empty
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, tuple) and r[0]:
            return r  # type: ignore[return-value]
    return None, None


async def fetch_missing(
    session: aiohttp.ClientSession,
    db: Session,
    papers: List[DiscoveredPaper],
) -> None:
    """Fill paper.abstract from cache when possible, fetch cache misses from
    free APIs, and write everything back to the cache.
    """
    candidates = [p for p in papers if p.doi and (not p.abstract or len(p.abstract) < MIN_ABSTRACT_LEN)]
    if not candidates:
        return

    # Map normalized DOI → paper(s)
    by_doi: Dict[str, List[DiscoveredPaper]] = {}
    for p in candidates:
        nd = _normalize_doi(p.doi)
        if nd:
            by_doi.setdefault(nd, []).append(p)

    # 1. Cache lookup
    cached = bulk_lookup(db, list(by_doi.keys()))
    cache_hits = 0
    for nd, entry in cached.items():
        if entry.abstract and len(entry.abstract) >= MIN_ABSTRACT_LEN:
            for paper in by_doi.get(nd, []):
                paper.abstract = entry.abstract
            cache_hits += 1

    # Build the set of DOIs that still need fetching (cache miss or unavailable-to-retry)
    to_fetch: List[str] = []
    for nd in by_doi.keys():
        entry = cached.get(nd)
        if not entry:
            to_fetch.append(nd)  # never tried
        elif entry.abstract and len(entry.abstract) >= MIN_ABSTRACT_LEN:
            continue  # already filled above
        elif entry.status == "unavailable":
            continue  # don't retry known failures (for now)
        else:
            to_fetch.append(nd)

    logger.info(
        "AbstractCache: %d hits, %d to fetch (from %d candidates)",
        cache_hits, len(to_fetch), len(candidates),
    )

    if not to_fetch:
        return

    # 2. Fetch misses with bounded parallelism
    sem = asyncio.Semaphore(MAX_PARALLEL_PER_SOURCE)

    async def run_one(doi: str) -> tuple[str, Optional[str], Optional[str]]:
        async with sem:
            abstract, source = await fetch_one(session, doi)
            return doi, abstract, source

    results = await asyncio.gather(
        *[run_one(doi) for doi in to_fetch],
        return_exceptions=True,
    )

    # 3. Apply results to papers + upsert to cache
    records: List[CachedAbstract] = []
    hits = 0
    for r in results:
        if isinstance(r, Exception):
            continue
        doi, abstract, source = r  # type: ignore[misc]
        if abstract:
            for paper in by_doi.get(doi, []):
                paper.abstract = abstract
            records.append(CachedAbstract(doi=doi, abstract=abstract, source=source, status="fresh"))
            hits += 1
        else:
            records.append(CachedAbstract(doi=doi, abstract=None, source=None, status="unavailable"))

    try:
        bulk_upsert(db, records)
    except Exception as e:
        logger.warning("AbstractCache: bulk_upsert failed: %s", e)

    logger.info(
        "AbstractCache: fetched %d/%d abstracts (hit rate %.0f%%)",
        hits, len(to_fetch), (hits / len(to_fetch) * 100) if to_fetch else 0,
    )


def write_back(db: Session, papers: List[DiscoveredPaper], source_label: str = "enricher") -> None:
    """Persist any paper abstracts that aren't already in the cache.

    Called after downstream enrichers (Landing, PDF) populate abstracts in memory,
    so subsequent searches can skip the expensive HTTP fetch.
    """
    rows: List[CachedAbstract] = []
    for p in papers:
        nd = _normalize_doi(p.doi)
        if nd and p.abstract and len(p.abstract) >= MIN_ABSTRACT_LEN:
            rows.append(CachedAbstract(doi=nd, abstract=p.abstract, source=source_label, status="fresh"))
    if not rows:
        return
    # Only write if there's no fresh record yet — don't overwrite a good cached value
    # with an enricher-extracted one (the fetch order already tried cache first).
    try:
        existing = bulk_lookup(db, [r.doi for r in rows])
        new_rows = [r for r in rows if existing.get(r.doi, CachedAbstract("", None, None, "none")).status != "fresh" or not existing[r.doi].abstract]
        if new_rows:
            bulk_upsert(db, new_rows)
            logger.info("AbstractCache: wrote back %d extracted abstracts", len(new_rows))
    except Exception as e:
        logger.warning("AbstractCache.write_back failed: %s", e)
