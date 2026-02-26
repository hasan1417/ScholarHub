"""Source-specific query builders for optimized search.

Each source has different query syntax capabilities. This module
provides formatters that optimize queries for each source's API.
"""

from __future__ import annotations

import re
import logging
from typing import List, Tuple

logger = logging.getLogger(__name__)

_STOPWORDS = frozenset({
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
    'of', 'with', 'by', 'from', 'is', 'are', 'was', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'can', 'shall', 'not', 'no', 'nor',
    'so', 'if', 'then', 'than', 'that', 'this', 'these', 'those', 'it',
    'its', 'as', 'up', 'out', 'about', 'into', 'over', 'after', 'before',
    'between', 'under', 'above', 'such', 'each', 'which', 'their', 'we',
    'how', 'what', 'when', 'where', 'who', 'why', 'use', 'using', 'based',
})


def _extract_quoted_phrases(query: str) -> Tuple[List[str], str]:
    """Extract quoted phrases from query and return (phrases, remainder)."""
    phrases = re.findall(r'"([^"]+)"', query)
    remainder = re.sub(r'"[^"]+"', ' ', query)
    remainder = re.sub(r'\s+', ' ', remainder).strip()
    return phrases, remainder


def _meaningful_words(query: str) -> List[str]:
    """Extract meaningful words from query, preserving academic acronyms."""
    return [w for w in query.split() if w.lower() not in _STOPWORDS and len(w) > 0]


def _is_short_phrase(query: str) -> bool:
    """Check if query is a short noun phrase (2-4 meaningful words)."""
    words = _meaningful_words(query)
    return 2 <= len(words) <= 4


def build_arxiv_query(query: str) -> str:
    """Build optimized arXiv query.

    arXiv supports:
    - Field prefixes: ti: (title), abs: (abstract), au: (author), all: (all fields)
    - Phrase matching with quotes
    - Boolean: AND, OR, ANDNOT

    Strategy:
    - Short queries (2-4 words): AND each word in title OR abstract
    - Quoted phrases: Preserve exact matching
    - Long queries: Use all: field
    """
    query = query.strip()
    if not query:
        return query

    phrases, remainder = _extract_quoted_phrases(query)

    # If we have explicit quoted phrases, use them
    if phrases:
        parts = []
        for phrase in phrases:
            parts.append(f'(ti:"{phrase}" OR abs:"{phrase}")')
        if remainder:
            parts.append(f'all:{remainder}')
        result = ' AND '.join(parts)
        logger.debug("[QueryBuilder] arXiv: '%s' → '%s' (quoted phrases)", query, result)
        return result

    # Short phrase: exact phrase match (primary) + individual words (fallback)
    if _is_short_phrase(query):
        words = _meaningful_words(query)
        phrase = ' '.join(words)
        phrase_part = f'(ti:"{phrase}" OR abs:"{phrase}")'
        word_parts = ' AND '.join(f'(ti:{w} OR abs:{w})' for w in words)
        result = f'{phrase_part} OR ({word_parts})'
        logger.debug("[QueryBuilder] arXiv: '%s' → '%s' (short phrase)", query, result)
        return result

    # Default: all fields
    result = f'all:{query}'
    logger.debug("[QueryBuilder] arXiv: '%s' → '%s' (default)", query, result)
    return result


def build_pubmed_query(query: str) -> str:
    """Build optimized PubMed query.

    PubMed supports field tags:
    - [Title/Abstract] or [tiab] - title or abstract
    - Automatic Term Mapping for plain text

    Strategy:
    - Short queries: AND each word in title/abstract
    - Quoted phrases: Preserve with [tiab] tag
    - Long queries: Plain text (PubMed's ATM handles it well)
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
        logger.debug("[QueryBuilder] PubMed: '%s' → '%s' (quoted phrases)", query, result)
        return result

    # Short phrase: exact phrase match (primary) + individual words (fallback)
    if _is_short_phrase(query):
        words = _meaningful_words(query)
        phrase = ' '.join(words)
        phrase_part = f'"{phrase}"[tiab]'
        word_part = ' AND '.join(f'{w}[tiab]' for w in words)
        result = f'{phrase_part} OR ({word_part})'
        logger.debug("[QueryBuilder] PubMed: '%s' → '%s' (short phrase)", query, result)
        return result

    # Default: plain text
    logger.debug("[QueryBuilder] PubMed: '%s' → unchanged (default)", query)
    return query


def build_europe_pmc_query(query: str) -> str:
    """Build optimized Europe PMC query.

    Europe PMC supports:
    - TITLE: and ABSTRACT: field prefixes
    - Phrase matching with quotes

    Strategy: only use field-specific search for explicit quoted phrases.
    Unquoted queries use plain text so Europe PMC's relevance engine
    can match across all indexed fields (full text, keywords, MeSH, etc.).
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
        logger.debug("[QueryBuilder] EuropePMC: '%s' → '%s' (quoted phrases)", query, result)
        return result

    # Plain text — let Europe PMC's own search engine handle relevance
    logger.debug("[QueryBuilder] EuropePMC: '%s' → unchanged (plain text)", query)
    return query


def build_sciencedirect_query(query: str) -> str:
    """Build optimized ScienceDirect (Elsevier) query.

    ScienceDirect supports:
    - TITLE(), ABS(), KEY() field functions
    - Boolean: AND, OR, NOT
    - Phrase matching with quotes

    Strategy:
    - Short queries: AND each word in TITLE or ABS
    - Quoted phrases: Exact match in TITLE or ABS
    - Long queries: Plain text
    """
    query = query.strip()
    if not query:
        return query

    phrases, remainder = _extract_quoted_phrases(query)

    if phrases:
        parts = []
        for phrase in phrases:
            parts.append(f'TITLE("{phrase}") OR ABS("{phrase}")')
        if remainder:
            parts.append(remainder)
        result = ' AND '.join(parts)
        logger.debug("[QueryBuilder] ScienceDirect: '%s' → '%s' (quoted phrases)", query, result)
        return result

    if _is_short_phrase(query):
        words = _meaningful_words(query)
        phrase = ' '.join(words)
        phrase_part = f'TITLE("{phrase}") OR ABS("{phrase}")'
        title_part = ' AND '.join(f'TITLE({w})' for w in words)
        abs_part = ' AND '.join(f'ABS({w})' for w in words)
        result = f'({phrase_part}) OR ({title_part}) OR ({abs_part})'
        logger.debug("[QueryBuilder] ScienceDirect: '%s' → '%s' (short phrase)", query, result)
        return result

    logger.debug("[QueryBuilder] ScienceDirect: '%s' → unchanged (default)", query)
    return query


def build_core_query(query: str) -> str:
    """Build optimized CORE query.

    CORE v3 uses Elasticsearch/Lucene syntax:
    - title:(word1 AND word2) for title-specific search
    - Phrase matching with quotes

    Strategy: only use field-specific search for explicit quoted phrases.
    Unquoted queries use plain text so CORE's full-text search can match
    across titles, abstracts, and full text.
    """
    query = query.strip()
    if not query:
        return query

    phrases, remainder = _extract_quoted_phrases(query)

    if phrases:
        parts = []
        for phrase in phrases:
            parts.append(f'title:"{phrase}"')
        if remainder:
            parts.append(remainder)
        result = ' AND '.join(parts)
        logger.debug("[QueryBuilder] CORE: '%s' → '%s' (quoted phrases)", query, result)
        return result

    # Plain text — let CORE's full-text search handle relevance
    logger.debug("[QueryBuilder] CORE: '%s' → unchanged (plain text)", query)
    return query
