"""Helpers for generating enhanced discovery queries."""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from app.services.paper_discovery.cache import LRUCache


logger = logging.getLogger(__name__)


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

        response = self.openai_client.chat.completions.create(
            model='gpt-5',
            messages=messages,
            temperature=0.2,
            max_tokens=256,
        )

        raw = (response.choices[0].message.content or '[]').strip()
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(item).strip() for item in data if str(item).strip()]
        except Exception:
            logger.debug("Failed to parse enhanced query JSON: %s", raw)

        return []
