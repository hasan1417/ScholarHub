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
    """Rank papers using an OpenAI Chat model by scoring relevance 0..1.

    Enhanced to consider:
    - Project context (query, scope, keywords)
    - Paper metadata (title, abstract, year, citations)
    - Recency and citation bonuses
    """

    def __init__(self, config: DiscoveryConfig):
        self.config = config
        # Use gpt-4o-mini by default - supports temperature and is cost-effective
        self.model_name = os.getenv("OPENAI_RERANK_MODEL", "gpt-4o-mini")

        # Scoring weights for post-processing bonuses
        self.recency_weight = 0.05  # Max 5% bonus for recent papers
        self.citation_weight = 0.05  # Max 5% bonus for highly cited papers
        self.pdf_bonus = 0.02  # 2% bonus for PDF availability

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
            logger.info("No OPENAI_API_KEY, falling back to SimpleRanker")
            return await SimpleRanker(self.config).rank(papers, query, target_text, target_keywords)

        try:
            # Prepare concise items for scoring
            items = []
            top_k = min(50, len(papers))
            current_year = datetime.now().year

            for idx, p in enumerate(papers[:top_k]):
                item = {
                    "id": idx,
                    "title": (p.title or "")[:256],
                    "abstract": (p.abstract or "")[:800],
                }
                # Include year and citations if available (helps GPT assess quality)
                if p.year:
                    item["year"] = p.year
                if p.citations_count and p.citations_count > 0:
                    item["citations"] = p.citations_count
                items.append(item)

            try:
                from openai import OpenAI  # type: ignore
            except Exception as exc:
                logger.info("OpenAI SDK unavailable: %s", exc)
                return await SimpleRanker(self.config).rank(papers, query, target_text, target_keywords)

            client = OpenAI(api_key=api_key)

            # Build rich project context
            project_context_parts = []
            if query:
                project_context_parts.append(f"Research Query: {query}")
            if target_text:
                project_context_parts.append(f"Project Scope: {target_text[:500]}")
            if target_keywords:
                project_context_parts.append(f"Keywords: {', '.join(target_keywords[:10])}")

            project_context = "\n".join(project_context_parts) if project_context_parts else query

            system = (
                "You are an expert academic research assistant. Your task is to score how relevant "
                "each paper is to a research project.\n\n"
                "Scoring criteria (0.0 to 1.0):\n"
                "- 0.9-1.0: Directly addresses the research topic, highly relevant methodology or findings\n"
                "- 0.7-0.8: Strongly related, covers key concepts or methods\n"
                "- 0.5-0.6: Moderately relevant, useful background or related work\n"
                "- 0.3-0.4: Tangentially related, might provide context\n"
                "- 0.0-0.2: Not relevant to the research project\n\n"
                "Consider: topic alignment, methodology relevance, and potential contribution to the research.\n"
                "Return ONLY a JSON array. Each element: {\"id\": number, \"score\": number}. No other text."
            )

            user_payload = {
                "project": project_context,
                "papers": items,
            }

            logger.info(f"GPT Ranker: scoring {len(items)} papers with {self.model_name}")

            resp = client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
                ],
                max_completion_tokens=2000,
            )
            content = (resp.choices[0].message.content or "[]").strip()

            # Handle potential markdown code blocks
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            # Parse JSON
            try:
                data = json.loads(content)
                scores_map = {
                    int(obj.get("id", -1)): float(obj.get("score", 0.0))
                    for obj in data if isinstance(obj, dict)
                }
                logger.debug(f"GPT Ranker: parsed {len(scores_map)} scores")
            except Exception as parse_err:
                logger.warning(f"Failed to parse GPT response: {parse_err}, content: {content[:200]}")
                scores_map = {}

            # Apply GPT scores + bonuses
            for idx, p in enumerate(papers):
                base_score = scores_map.get(idx, 0.0)

                # Apply bonuses for papers that were scored
                if idx < top_k and base_score > 0:
                    bonus = 0.0

                    # Recency bonus: papers from last 3 years get up to 5% bonus
                    if p.year and p.year >= current_year - 3:
                        years_old = current_year - p.year
                        recency_factor = 1 - (years_old / 3)  # 1.0 for current year, 0 for 3 years old
                        bonus += self.recency_weight * recency_factor

                    # Citation bonus: log-scaled, capped at 5%
                    if p.citations_count and p.citations_count > 0:
                        import math
                        citation_factor = min(1.0, math.log10(1 + p.citations_count) / 3)  # ~1000 citations = max
                        bonus += self.citation_weight * citation_factor

                    # PDF availability bonus
                    if p.pdf_url:
                        bonus += self.pdf_bonus

                    base_score = min(1.0, base_score + bonus)

                p.relevance_score = max(0.0, min(1.0, float(base_score)))

            ranked = sorted(papers, key=lambda p: p.relevance_score, reverse=True)
            logger.info(f"GPT Ranker: ranked {len(papers)} papers, top score: {ranked[0].relevance_score if ranked else 0}")
            return ranked

        except Exception as exc:
            logger.warning(f"GPT ranking failed, falling back to SimpleRanker: {exc}")
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
