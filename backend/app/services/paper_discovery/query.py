"""Helpers for query understanding and core-term extraction."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import List, Set

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


# ---------------------------------------------------------------------------
# Query Understanding — replaces the old QueryEnhancer
# ---------------------------------------------------------------------------

@dataclass
class QueryIntent:
    """Structured understanding of an academic search query."""
    interpreted_query: str  # Natural language description for the ranker
    search_terms: List[str] = field(default_factory=list)  # Better search phrasings


_intent_cache = LRUCache(max_size=200, ttl_seconds=3600)

_UNDERSTAND_SYSTEM = (
    "You are an academic search query interpreter. "
    "Given a research query, identify if it contains compound concepts, model names, "
    "technique combinations, or domain-specific terms that should be kept together.\n\n"
    "Return ONLY compact single-line JSON, no markdown:\n"
    '{"interpreted_query":"...","search_terms":["...","..."]}\n\n'
    "- interpreted_query: A clear description of what the user is actually looking for.\n"
    "- search_terms: 1-2 alternative search phrasings that better capture the intent "
    "(omit the original query). Empty array if the query is already clear.\n\n"
    "Examples:\n"
    '- "Arabic character BERT" → {"interpreted_query":"CharacterBERT (a BERT variant using character-level CNN instead of WordPiece tokenization) applied to Arabic language","search_terms":["CharacterBERT Arabic","character-level BERT Arabic NLP"]}\n'
    '- "graph neural network" → {"interpreted_query":"graph neural networks","search_terms":[]}\n'
    '- "federated learning privacy" → {"interpreted_query":"privacy-preserving techniques in federated learning","search_terms":["federated learning differential privacy"]}\n'
    '- "transformer attention" → {"interpreted_query":"attention mechanisms in transformer models","search_terms":[]}\n'
)


async def understand_query(query: str) -> QueryIntent:
    """Use a fast LLM call to understand compound academic concepts in a query.

    Returns a QueryIntent with semantic interpretation and better search terms.
    Falls back to the original query on any failure.
    """
    query = (query or "").strip()
    if not query:
        return QueryIntent(interpreted_query=query)

    # Short-circuit: 1-2 word queries don't need LLM understanding
    if len(query.split()) <= 2:
        return QueryIntent(interpreted_query=query)

    # Check cache
    cached = await _intent_cache.get(query)
    if cached is not None:
        logger.debug("[QueryIntent] Cache hit for '%s'", query)
        return cached

    try:
        from openai import AsyncOpenAI
        from app.core.config import settings

        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            intent = QueryIntent(interpreted_query=query)
            await _intent_cache.set(query, intent)
            return intent

        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub",
            },
        )

        # Retry once on timeout — reasoning models can be slow on first call
        last_exc = None
        for attempt in range(2):
            try:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(
                        model="openai/gpt-5-mini",
                        messages=[
                            {"role": "system", "content": _UNDERSTAND_SYSTEM},
                            {"role": "user", "content": query},
                        ],
                        max_completion_tokens=512,
                        temperature=0.0,
                    ),
                    timeout=8.0,
                )
                break
            except asyncio.TimeoutError:
                last_exc = asyncio.TimeoutError()
                logger.warning("[QueryIntent] Timeout for '%s' (attempt %d)", query, attempt + 1)
                continue
        else:
            raise last_exc  # type: ignore[misc]

        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        # Extract first JSON object if model returned extra data
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try extracting first {...} block
            match = re.search(r'\{[^{}]*\}', raw)
            if match:
                data = json.loads(match.group())
            else:
                raise
        intent = QueryIntent(
            interpreted_query=data.get("interpreted_query", query),
            search_terms=[s for s in data.get("search_terms", []) if s and s != query],
        )
        logger.info(
            "[QueryIntent] '%s' → interpreted='%s', search_terms=%s",
            query, intent.interpreted_query, intent.search_terms,
        )
        await _intent_cache.set(query, intent)
        return intent

    except Exception as exc:
        logger.warning("[QueryIntent] Failed for '%s': %s", query, exc)
        intent = QueryIntent(interpreted_query=query)
        await _intent_cache.set(query, intent)
        return intent
