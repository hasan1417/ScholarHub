"""Helpers for generating enhanced discovery queries."""

from __future__ import annotations

import json
import logging
import re
from typing import List, Optional, Set

from app.services.paper_discovery.cache import LRUCache


logger = logging.getLogger(__name__)


# Common stopwords to exclude from core terms
_STOPWORDS = frozenset({
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
    'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'been', 'be', 'have',
    'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may',
    'might', 'must', 'shall', 'can', 'need', 'about', 'into', 'through', 'during',
    'before', 'after', 'above', 'below', 'between', 'under', 'again', 'further',
    'then', 'once', 'here', 'there', 'when', 'where', 'why', 'how', 'all', 'each',
    'few', 'more', 'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'just', 'also', 'now', 'using',
    'based', 'study', 'research', 'paper', 'papers', 'approach', 'method', 'methods',
    'analysis', 'results', 'review', 'new', 'novel', 'recent', 'latest',
})


def extract_core_terms(query: str) -> Set[str]:
    """Extract core terms from the original query for relevance boosting.

    Core terms are:
    - Individual meaningful words (not stopwords, length > 2)
    - Quoted phrases preserved as single terms

    Returns a set of lowercase terms.
    """
    if not query:
        return set()

    query = query.strip()
    core_terms: Set[str] = set()

    # Extract quoted phrases first (preserve as single terms)
    quoted_pattern = r'"([^"]+)"'
    quoted_phrases = re.findall(quoted_pattern, query)
    for phrase in quoted_phrases:
        phrase_clean = phrase.strip().lower()
        if phrase_clean and len(phrase_clean) > 2:
            core_terms.add(phrase_clean)

    # Remove quoted phrases from query for word extraction
    query_without_quotes = re.sub(quoted_pattern, ' ', query)

    # Extract individual words
    query_clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', query_without_quotes).lower()
    words = query_clean.split()

    for word in words:
        word = word.strip()
        if len(word) > 2 and word not in _STOPWORDS:
            core_terms.add(word)

    logger.debug(f"[CoreTerms] query='{query}' → terms={core_terms}")
    return core_terms


class QueryEnhancer:
    """Produce enriched search queries using optional LLM assistance."""

    def __init__(self, openai_client=None) -> None:
        self.openai_client = openai_client
        self.cache = LRUCache(max_size=100, ttl_seconds=3600)

    async def enhance_query(
        self,
        query: str,
        research_topic: Optional[str] = None,
        max_queries: int = 3,
    ) -> List[str]:
        """Return a list of refined queries (prefixed with the original)."""

        query = (query or '').strip()
        if not query and not research_topic:
            logger.warning("QueryEnhancer received empty query and no topic")
            return ['']

        if len(query.split()) <= 2 and not research_topic:
            return [query]

        cache_key = f"{query}::{research_topic or ''}::{max_queries}"
        cached = await self.cache.get(cache_key)
        if cached:
            return cached

        if not self.openai_client:
            baseline = [q for q in [query, research_topic] if q]
            result = baseline or [query]
            await self.cache.set(cache_key, result)
            return result

        try:
            enhanced = await self._generate_with_gpt(query, research_topic, max_queries)
            final = [query] + [q for q in enhanced if q and q != query]
            await self.cache.set(cache_key, final)
            return final
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Query enhancement failed: %s", exc)
            fallback = [q for q in [query, research_topic] if q]
            return fallback or [query]

    async def _generate_with_gpt(
        self,
        query: str,
        research_topic: Optional[str],
        max_queries: int,
    ) -> List[str]:
        """Call the OpenAI client to obtain query variations."""

        prompt_parts = [
            "You are an expert research assistant.",
            "Given a base query, propose additional academic search queries.",
            "Return a JSON array of strings.",
        ]
        if research_topic:
            prompt_parts.append(f"Research topic: {research_topic}")
        prompt_parts.append(f"Base query: {query}")
        prompt_parts.append(f"Generate up to {max_queries} diverse queries.")

        messages = [
            {"role": "system", "content": prompt_parts[0]},
            {"role": "user", "content": "\n".join(prompt_parts[1:])},
        ]

        # Use gpt-4o-mini for query enhancement - fast and cost-effective
        # Note: reasoning models (gpt-5, o3, o4) don't support temperature
        response = self.openai_client.responses.create(
            model='gpt-4o-mini',
            input=messages,
            temperature=0.2,
            max_output_tokens=256,
        )

        raw = (response.output_text or '[]').strip()
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
        except Exception:
            logger.debug("Failed to parse enhanced query JSON: %s", raw)

        return []
