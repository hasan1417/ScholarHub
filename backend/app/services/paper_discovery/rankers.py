"""Ranking strategies for paper discovery results."""

from __future__ import annotations

import asyncio
import io
import json
import logging
import os
from datetime import datetime
from typing import List, Optional, Set

import aiohttp

from app.services.paper_discovery.config import DiscoveryConfig
from app.services.paper_discovery.interfaces import PaperRanker
from app.services.paper_discovery.models import DiscoveredPaper

logger = logging.getLogger(__name__)

class LexicalRanker(PaperRanker):
    """Lexical-based paper ranking"""
    
    def __init__(self, config: DiscoveryConfig):
        self.config = config
    
    async def rank(
        self,
        papers: List[DiscoveredPaper],
        query: str,
        target_text: Optional[str] = None,
        target_keywords: Optional[List[str]] = None,
        **kwargs
    ) -> List[DiscoveredPaper]:
        """Rank papers using lexical similarity"""
        
        def tokenize(text: str) -> Set[str]:
            import re
            text = (text or '').lower()
            text = re.sub(r'[^a-z0-9\s]', ' ', text)
            return set(w for w in text.split() if len(w) > 2)
        
        query_tokens = tokenize(target_text or query)
        keyword_set = set((kw or '').lower() for kw in (target_keywords or []))
        
        weights = self.config.ranking_weights

        raw_scores: List[float] = []

        for paper in papers:
            title_tokens = tokenize(paper.title)
            abstract_tokens = tokenize(paper.abstract)
            
            # Calculate overlaps
            title_overlap = len(title_tokens & query_tokens) / max(1, len(title_tokens))
            abstract_overlap = len(abstract_tokens & query_tokens) / max(1, len(abstract_tokens))
            kw_title_overlap = len(title_tokens & keyword_set) / max(1, len(keyword_set)) if keyword_set else 0
            kw_abstract_overlap = len(abstract_tokens & keyword_set) / max(1, len(keyword_set)) if keyword_set else 0
            
            # Base score
            score = (
                weights['title_overlap'] * title_overlap +
                weights['abstract_overlap'] * abstract_overlap +
                weights['keyword_title'] * kw_title_overlap +
                weights['keyword_body'] * kw_abstract_overlap
            )
            
            # Bonuses
            if paper.year:
                age = datetime.now().year - paper.year
                recency_score = max(0, 1 - age / 10)  # Decay over 10 years
                score += weights['recency_max'] * recency_score
            
            if paper.citations_count and paper.citations_count > 0:
                import math
                citation_score = min(1, math.log(1 + paper.citations_count) / 10)
                score += weights['citations_max'] * citation_score
            
            if paper.pdf_url:
                score += weights['pdf_bonus']
            elif paper.is_open_access:
                score += weights['oa_bonus']
            
            raw_scores.append(max(0.0, score))

        max_score = max(raw_scores, default=0.0)
        min_score = min(raw_scores, default=0.0)
        span = max_score - min_score

        for paper, raw in zip(papers, raw_scores):
            if max_score <= 0:
                paper.relevance_score = 0.0
                continue
            if span > 0:
                normalized = (raw - min_score) / span
            else:
                normalized = 1.0
            paper.relevance_score = float(min(1.0, max(0.0, normalized)))
        
        return sorted(papers, key=lambda p: p.relevance_score, reverse=True)


class SimpleRanker(PaperRanker):
    """Minimal scoring: title-token overlap with the query only."""

    def __init__(self, config: DiscoveryConfig):
        self.config = config

    async def rank(
        self,
        papers: List[DiscoveredPaper],
        query: str,
        target_text: Optional[str] = None,
        target_keywords: Optional[List[str]] = None,
        **kwargs
    ) -> List[DiscoveredPaper]:
        def tokenize(text: str) -> Set[str]:
            import re
            text = (text or '').lower()
            text = re.sub(r'[^a-z0-9\s]', ' ', text)
            return set(w for w in text.split() if len(w) > 2)

        query_tokens = tokenize(target_text or query)
        raw_scores: List[float] = []

        for paper in papers:
            title_tokens = tokenize(paper.title)
            if not title_tokens:
                raw_scores.append(0.0)
                continue

            hits = len(title_tokens & query_tokens)
            title_ratio = hits / max(1, len(title_tokens))
            query_ratio = hits / max(1, len(query_tokens)) if query_tokens else 0.0
            combined = 0.6 * title_ratio + 0.4 * query_ratio if query_tokens else title_ratio
            raw_scores.append(max(0.0, combined))

        max_score = max(raw_scores, default=0.0)
        min_score = min(raw_scores, default=0.0)
        span = max_score - min_score

        for paper, raw in zip(papers, raw_scores):
            if max_score <= 0:
                paper.relevance_score = 0.0
                continue
            if span > 0:
                normalized = (raw - min_score) / span
            else:
                normalized = 1.0
            paper.relevance_score = float(min(1.0, max(0.0, normalized)))

        return sorted(papers, key=lambda p: p.relevance_score, reverse=True)


class GptRanker(PaperRanker):
    """Rank papers using an OpenAI Chat model by scoring relevance 0..1."""

    def __init__(self, config: DiscoveryConfig):
        self.config = config
        self.model_name = os.getenv("OPENAI_RERANK_MODEL", "gpt-5")

    async def rank(
        self,
        papers: List[DiscoveredPaper],
        query: str,
        target_text: Optional[str] = None,
        target_keywords: Optional[List[str]] = None,
        **kwargs
    ) -> List[DiscoveredPaper]:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            # Fallback to simple ranker if no key
            return await SimpleRanker(self.config).rank(papers, query, target_text, target_keywords)

        try:
            # Prepare concise items for scoring
            items = []
            top_k = min(50, len(papers))
            for idx, p in enumerate(papers[:top_k]):
                items.append({
                    "id": idx,
                    "title": (p.title or "")[:256],
                    "abstract": (p.abstract or "")[:1024],
                    "year": p.year or "",
                    "source": p.source or "",
                })

            try:
                from openai import OpenAI  # type: ignore
            except Exception as exc:  # pragma: no cover
                logger.info("OpenAI SDK unavailable: %s", exc)
                return await SimpleRanker(self.config).rank(papers, query, target_text, target_keywords)

            client = OpenAI(api_key=api_key)
            system = (
                "You are a helpful academic assistant. Given a query and a list of items, "
                "return a JSON array. Each element must be {id: number, score: number in [0,1]} only."
            )
            user_payload = {
                "query": target_text or query,
                "items": items,
                "instruction": "Return only JSON array of {id, score}. No extra text.",
            }
            resp = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user_payload)},
                ],
                temperature=0.0,
                max_tokens=400,
            )
            content = (resp.choices[0].message.content or "[]").strip()

            # Parse JSON
            try:
                data = json.loads(content)
                scores_map = {
                    int(obj.get("id", -1)): float(obj.get("score", 0.0))
                    for obj in data if isinstance(obj, dict)
                }
            except Exception:
                scores_map = {}

            # Apply scores to the first top_k items; others keep 0
            for idx, p in enumerate(papers):
                s = scores_map.get(idx)
                if s is None:
                    # backfill with a tiny baseline to maintain ordering stability
                    s = 0.0
                p.relevance_score = max(0.0, min(1.0, float(s)))

            return sorted(papers, key=lambda p: p.relevance_score, reverse=True)
        except Exception as exc:  # pragma: no cover
            logger.info("GPT ranking failed; falling back to simple: %s", exc)
            return await SimpleRanker(self.config).rank(papers, query, target_text, target_keywords)

    

    async def _fetch_pdf_snippets(self, session: aiohttp.ClientSession, papers: List[DiscoveredPaper]) -> List[str]:
        async def fetch_and_extract(paper: DiscoveredPaper) -> str:
            try:
                if not paper.pdf_url:
                    return ""
                async with session.get(paper.pdf_url) as resp:
                    if resp.status != 200:
                        return ""
                    data = await resp.read()
                # Lightweight extraction: rely on PyPDF2 already in deps
                import PyPDF2
                text_segments: List[str] = []
                with io.BytesIO(data) as bio:
                    reader = PyPDF2.PdfReader(bio)
                    # Default to first 3 pages after purge
                    num_pages = min(3, len(reader.pages))
                    for i in range(num_pages):
                        try:
                            page = reader.pages[i]
                            text = page.extract_text() or ""
                            text_segments.append(text)
                        except Exception:
                            continue
                snippet = " ".join(seg.strip() for seg in text_segments if seg).strip()
                # Trim overly long snippets
                return snippet[:4000]
            except Exception:
                return ""

        results = await asyncio.gather(*[fetch_and_extract(p) for p in papers], return_exceptions=True)
        output: List[str] = []
        for r in results:
            try:
                output.append(str(r)) if not isinstance(r, Exception) else output.append("")
            except Exception:
                output.append("")
        return output


# ============= Orchestrator Service =============
