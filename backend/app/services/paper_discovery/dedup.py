"""Deduplicate and merge papers from multiple sources.

The discovery pipeline receives the same work from multiple indexes
(arXiv preprint + Crossref published record + Semantic Scholar copy + …).
This module collapses those into one record per work, always preferring the
published version while preserving useful bits from the others (notably the
arXiv free PDF URL).

Matching rules (a paper is the same work if ANY key matches):
  - Normalized DOI (treating "https://doi.org/X" and "X" identically,
    and stripping double-prefixed garbage seen in some OpenAlex responses)
  - arXiv ID (version-stripped)
  - Normalized title + year
  - Normalized title alone (fallback when year is missing)

Preference rules for picking the winner in a duplicate group:
  1. Published DOI (non-arXiv) beats arXiv DOI beats no DOI.
  2. Within a tier, the source with richer metadata wins (completeness score).
  3. Stable tiebreaker: the earlier-arriving paper.

Merge rules:
  - Winner keeps its identity fields (title, authors, DOI, journal, year).
  - Gaps in winner are filled from loser: abstract, pdf_url, open_access_url,
    citations_count (max), is_open_access (OR), keywords (union).
  - `merged_sources` records every source that returned this work.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from app.services.paper_discovery.models import (
    DiscoveredPaper,
    _is_arxiv_doi,
    _normalize_doi,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Preference scoring
# ---------------------------------------------------------------------------

def _publication_tier(p: DiscoveredPaper) -> int:
    """3 = published with DOI; 1 = arXiv preprint; 0 = no DOI (usually title-only)."""
    if p.doi:
        return 1 if _is_arxiv_doi(p.doi) else 3
    if p.arxiv_id:
        return 1  # arXiv record without published DOI yet
    return 0


def _completeness_score(p: DiscoveredPaper) -> int:
    """Tiebreaker within a publication tier. Higher = more complete metadata."""
    score = 0
    if p.abstract and len(p.abstract) >= 50:
        score += 4
    if p.pdf_url:
        score += 3
    if p.is_open_access:
        score += 2
    if p.year:
        score += 1
    if p.authors:
        score += 1
    if p.citations_count and p.citations_count > 0:
        score += 1
    if p.journal:
        score += 1
    return score


def _paper_rank(p: DiscoveredPaper) -> Tuple[int, int]:
    """Composite rank: (tier, completeness). Higher wins."""
    return (_publication_tier(p), _completeness_score(p))


# ---------------------------------------------------------------------------
# Union-find (disjoint set) — lets us group papers sharing ANY match key
# ---------------------------------------------------------------------------

class _UnionFind:
    __slots__ = ("_parent",)

    def __init__(self) -> None:
        self._parent: Dict[int, int] = {}

    def find(self, x: int) -> int:
        root = x
        while self._parent.get(root, root) != root:
            root = self._parent[root]
        # Path compression
        while self._parent.get(x, x) != root:
            nxt = self._parent[x]
            self._parent[x] = root
            x = nxt
        return root

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self._parent[ra] = rb


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------

def _merge_into(winner: DiscoveredPaper, loser: DiscoveredPaper) -> None:
    """Fold useful data from `loser` into `winner` in-place."""
    # Abstract: keep the longer, more substantive one (both papers may have
    # abstracts from different sources with different completeness).
    if (not winner.abstract or len(winner.abstract) < len(loser.abstract or "")) and loser.abstract:
        winner.abstract = loser.abstract

    # PDF URL: prefer whatever's already there, but arXiv PDFs are free and
    # reliable — if the winner has no PDF URL, take the loser's.
    if not winner.pdf_url and loser.pdf_url:
        winner.pdf_url = loser.pdf_url

    if not winner.open_access_url and loser.open_access_url:
        winner.open_access_url = loser.open_access_url

    if loser.is_open_access:
        winner.is_open_access = True

    # Citations: take the max (some sources report stale or partial counts).
    wc = winner.citations_count or 0
    lc = loser.citations_count or 0
    if lc > wc:
        winner.citations_count = lc

    # Fill gaps in identity fields only if the winner is actually missing them.
    if not winner.year and loser.year:
        winner.year = loser.year
    if not winner.authors and loser.authors:
        winner.authors = list(loser.authors)
    if not winner.journal and loser.journal:
        winner.journal = loser.journal
    if not winner.url and loser.url:
        winner.url = loser.url
    if not winner.arxiv_id and loser.arxiv_id:
        winner.arxiv_id = loser.arxiv_id

    # Keywords: union
    if loser.keywords:
        existing = {k.lower() for k in (winner.keywords or [])}
        for kw in loser.keywords:
            if kw and kw.lower() not in existing:
                winner.keywords.append(kw)
                existing.add(kw.lower())

    # If the winner has no DOI but the loser does, upgrade — unless the loser's
    # DOI is an arXiv-assigned one and the winner already has a better path
    # (non-arXiv DOI or published arxiv_id waiting). The rank check before merge
    # usually handles tier selection, but an arXiv winner + published loser can
    # happen when keys matched on title alone.
    if not winner.doi and loser.doi:
        winner.doi = loser.doi
    elif winner.doi and _is_arxiv_doi(winner.doi) and loser.doi and not _is_arxiv_doi(loser.doi):
        # We should swap — the loser actually had the published DOI, which
        # means the rank comparison missed something. Correct it.
        winner.doi = loser.doi

    # Source tracking
    if loser.source and loser.source not in winner.merged_sources:
        winner.merged_sources.append(loser.source)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _fuzzy_title_similarity(a: str, b: str) -> float:
    """Fast, dependency-free similarity score for two normalized titles.

    Uses Jaccard on word sets — close enough for the "same work, different
    venue" case we want to catch (e.g. *"Protein language model supervised
    motif-scaffolding design with GPDL"* vs *"Protein Language Model
    Supervised Scalable Approach for Diverse and Designable Protein
    Motif-Scaffolding with GPDL"*). Avoids bringing in Levenshtein/rapidfuzz.
    """
    if not a or not b:
        return 0.0
    wa = set(a.split())
    wb = set(b.split())
    if not wa or not wb:
        return 0.0
    inter = wa & wb
    union = wa | wb
    return len(inter) / len(union)


def dedupe_papers(papers: List[DiscoveredPaper]) -> Tuple[List[DiscoveredPaper], int]:
    """Group duplicate papers, merge them, and return the deduped list.

    Returns `(deduped_papers, num_collapsed)` where `num_collapsed` is the
    count of duplicate records that were merged away (input - output).
    """
    if not papers:
        return [], 0

    n = len(papers)
    uf = _UnionFind()

    # Build an index from every match key to the paper indices that carry it.
    # Then union all indices that share a key.
    key_to_indices: Dict[str, List[int]] = {}
    for i, p in enumerate(papers):
        for key in p.match_keys():
            key_to_indices.setdefault(key, []).append(i)

    for indices in key_to_indices.values():
        if len(indices) > 1:
            first = indices[0]
            for j in indices[1:]:
                uf.union(first, j)

    # Fuzzy fallback — catches "same work, different venue" where titles have
    # been rephrased (e.g. preprint vs published) or doubled with a subtitle.
    # Only apply to papers that still have unique match keys (didn't already
    # unify via DOI/arxiv/title+year) and whose years agree within ±1. The
    # O(n^2) scan is bounded at typical n ~ 200 results per search.
    from app.services.paper_discovery.models import _normalize_title
    _FUZZY_THRESHOLD = 0.75
    normalized_titles: List[str] = [_normalize_title(p.title or "") for p in papers]
    for i in range(n):
        ti = normalized_titles[i]
        if not ti or len(ti) < 15:
            continue
        yi = papers[i].year
        for j in range(i + 1, n):
            tj = normalized_titles[j]
            if not tj or len(tj) < 15:
                continue
            if uf.find(i) == uf.find(j):
                continue  # already unified
            yj = papers[j].year
            if yi and yj and abs(yi - yj) > 1:
                continue
            if _fuzzy_title_similarity(ti, tj) >= _FUZZY_THRESHOLD:
                uf.union(i, j)
                logger.debug(
                    "dedup fuzzy-title union: '%s' == '%s'",
                    (papers[i].title or "")[:60], (papers[j].title or "")[:60],
                )

    # Collect groups
    groups: Dict[int, List[int]] = {}
    for i in range(n):
        root = uf.find(i)
        groups.setdefault(root, []).append(i)

    deduped: List[DiscoveredPaper] = []
    collapsed = 0
    for members in groups.values():
        if len(members) == 1:
            paper = papers[members[0]]
            # Seed merged_sources with the paper's own source so downstream
            # consumers always see the full provenance.
            if paper.source and not paper.merged_sources:
                paper.merged_sources = [paper.source]
            deduped.append(paper)
            continue

        # Sort members by preference: highest tier+completeness first.
        members_sorted = sorted(members, key=lambda idx: _paper_rank(papers[idx]), reverse=True)
        winner = papers[members_sorted[0]]
        if not winner.merged_sources:
            winner.merged_sources = [winner.source] if winner.source else []

        for loser_idx in members_sorted[1:]:
            loser = papers[loser_idx]
            _merge_into(winner, loser)
            collapsed += 1
            logger.debug(
                "dedup merged '%s' [%s → %s] (tiers %d<-%d)",
                (winner.title or "")[:60],
                loser.source,
                winner.source,
                _publication_tier(winner),
                _publication_tier(loser),
            )

        deduped.append(winner)

    return deduped, collapsed
