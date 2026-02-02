"""Source-specific query builders for optimized search.

Each source has different query syntax capabilities. This module
provides formatters that optimize queries for each source's API.
"""

from __future__ import annotations

import re
import logging
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


def _extract_quoted_phrases(query: str) -> Tuple[List[str], str]:
    """Extract quoted phrases from query and return (phrases, remainder)."""
    phrases = re.findall(r'"([^"]+)"', query)
    remainder = re.sub(r'"[^"]+"', ' ', query)
    remainder = re.sub(r'\s+', ' ', remainder).strip()
    return phrases, remainder


def _is_short_phrase(query: str) -> bool:
    """Check if query is a short noun phrase (2-3 meaningful words)."""
    words = [w for w in query.split() if len(w) > 2]
    return 2 <= len(words) <= 3


def build_arxiv_query(query: str) -> str:
    """Build optimized arXiv query.

    arXiv supports:
    - Field prefixes: ti: (title), abs: (abstract), au: (author), all: (all fields)
    - Phrase matching with quotes
    - Boolean: AND, OR, ANDNOT

    Strategy:
    - Short queries (2-3 words): Search title OR abstract with phrase matching
    - Quoted phrases: Preserve exact matching
    - Long queries: Use all: field (current behavior)
    """
    query = query.strip()
    if not query:
        return query

    phrases, remainder = _extract_quoted_phrases(query)

    # If we have explicit quoted phrases, use them
    if phrases:
        parts = []
        for phrase in phrases:
            # Search phrase in title or abstract
            parts.append(f'(ti:"{phrase}" OR abs:"{phrase}")')
        if remainder:
            parts.append(f'all:{remainder}')
        result = ' AND '.join(parts)
        logger.debug(f"[QueryBuilder] arXiv: '{query}' → '{result}' (quoted phrases)")
        return result

    # Short phrase: try title + abstract matching
    if _is_short_phrase(query):
        # Quote the phrase for exact matching in title OR abstract
        result = f'(ti:"{query}" OR abs:"{query}")'
        logger.debug(f"[QueryBuilder] arXiv: '{query}' → '{result}' (short phrase)")
        return result

    # Default: all fields (current behavior)
    result = f'all:{query}'
    logger.debug(f"[QueryBuilder] arXiv: '{query}' → '{result}' (default)")
    return result


def build_pubmed_query(query: str) -> str:
    """Build optimized PubMed query.

    PubMed supports field tags:
    - [Title] or [ti] - title field
    - [Title/Abstract] or [tiab] - title or abstract
    - [MeSH Terms] - medical subject headings

    Strategy:
    - Short queries: Search title/abstract
    - Quoted phrases: Preserve with [tiab] tag
    - Long queries: Plain text (PubMed's default is good)
    """
    query = query.strip()
    if not query:
        return query

    phrases, remainder = _extract_quoted_phrases(query)

    if phrases:
        parts = []
        for phrase in phrases:
            parts.append(f'"{phrase}"[tiab]')
        if remainder:
            parts.append(remainder)
        result = ' AND '.join(parts)
        logger.debug(f"[QueryBuilder] PubMed: '{query}' → '{result}' (quoted phrases)")
        return result

    # Short phrase: search in title/abstract
    if _is_short_phrase(query):
        result = f'"{query}"[tiab]'
        logger.debug(f"[QueryBuilder] PubMed: '{query}' → '{result}' (short phrase)")
        return result

    # Default: plain text (PubMed handles it well)
    logger.debug(f"[QueryBuilder] PubMed: '{query}' → unchanged (default)")
    return query


def build_europe_pmc_query(query: str) -> str:
    """Build optimized Europe PMC query.

    Europe PMC supports similar syntax to PubMed:
    - TITLE: field prefix
    - ABSTRACT: field prefix
    - Phrase matching with quotes

    Strategy similar to PubMed.
    """
    query = query.strip()
    if not query:
        return query

    phrases, remainder = _extract_quoted_phrases(query)

    if phrases:
        parts = []
        for phrase in phrases:
            parts.append(f'(TITLE:"{phrase}" OR ABSTRACT:"{phrase}")')
        if remainder:
            parts.append(remainder)
        result = ' AND '.join(parts)
        logger.debug(f"[QueryBuilder] EuropePMC: '{query}' → '{result}' (quoted phrases)")
        return result

    # Short phrase: search in title/abstract
    if _is_short_phrase(query):
        result = f'(TITLE:"{query}" OR ABSTRACT:"{query}")'
        logger.debug(f"[QueryBuilder] EuropePMC: '{query}' → '{result}' (short phrase)")
        return result

    # Default: plain text
    logger.debug(f"[QueryBuilder] EuropePMC: '{query}' → unchanged (default)")
    return query


def build_openalex_query(query: str) -> str:
    """Build OpenAlex query.

    OpenAlex uses simple text search which works well.
    Their API handles phrase matching internally.

    No optimization needed - pass through.
    """
    return query.strip()


def build_crossref_query(query: str) -> str:
    """Build Crossref query.

    Crossref's query parameter works well with plain text.
    Could use query.bibliographic for better bibliographic search.

    No optimization needed - pass through.
    """
    return query.strip()


def build_semantic_scholar_query(query: str) -> str:
    """Build Semantic Scholar query.

    Semantic Scholar has excellent NLP-based search.
    Plain text works best - let their system handle it.

    No optimization needed - pass through.
    """
    return query.strip()
