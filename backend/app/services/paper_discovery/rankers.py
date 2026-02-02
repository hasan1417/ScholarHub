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
    """Enhanced scoring: relevance + citations + recency, plus core term boosts.

    Scoring formula (Phase 2.1):
    - 50% relevance (title/query overlap + core term boosts)
    - 30% citations (log-scaled, recency-adjusted)
    - 20% recency (papers from last 5 years get bonus)
    """

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
        import math

        # Extract core_terms from kwargs (passed from orchestrator)
        core_terms: Set[str] = kwargs.get('core_terms', set())
        current_year = datetime.now().year

        def tokenize(text: str) -> Set[str]:
            import re
            text = (text or '').lower()
            text = re.sub(r'[^a-z0-9\s]', ' ', text)
            return set(w for w in text.split() if len(w) > 2)

        query_tokens = tokenize(target_text or query)
        weights = self.config.ranking_weights

        # Collect scores for normalization
        relevance_scores: List[float] = []
        citation_scores: List[float] = []
        recency_scores: List[float] = []

        for paper in papers:
            title_tokens = tokenize(paper.title)
            abstract_tokens = tokenize(paper.abstract) if paper.abstract else set()

            # --- Relevance score (title overlap + core term boosts) ---
            if not title_tokens:
                relevance_scores.append(0.0)
                citation_scores.append(0.0)
                recency_scores.append(0.0)
                continue

            hits = len(title_tokens & query_tokens)
            title_ratio = hits / max(1, len(title_tokens))
            query_ratio = hits / max(1, len(query_tokens)) if query_tokens else 0.0
            relevance = 0.6 * title_ratio + 0.4 * query_ratio if query_tokens else title_ratio

            # Apply core term boosts (Phase 1.3)
            core_boost = 0.0
            if core_terms:
                title_text = (paper.title or '').lower()
                abstract_text = (paper.abstract or '').lower()

                for term in core_terms:
                    if term in title_text or term in title_tokens:
                        core_boost += weights.get('core_term_title_boost', 0.20)
                        break

                for term in core_terms:
                    if term in abstract_text or term in abstract_tokens:
                        core_boost += weights.get('core_term_abstract_boost', 0.10)
                        break

            relevance_scores.append(max(0.0, relevance + core_boost))

            # --- Citation score (log-scaled, recency-adjusted) ---
            citations = paper.citations_count or 0
            if citations > 0 and paper.year:
                years_since = max(1, current_year - paper.year + 1)
                # Recency-adjusted: citations / log(years + 1)
                # This prevents old highly-cited papers from dominating
                adjusted_citations = citations / math.log(years_since + 1)
                # Log scale to prevent mega-papers from dominating
                citation_score = math.log10(1 + adjusted_citations) / 4  # ~10000 adjusted = 1.0
            elif citations > 0:
                citation_score = math.log10(1 + citations) / 4
            else:
                citation_score = 0.0
            citation_scores.append(min(1.0, citation_score))

            # --- Recency score (papers from last 5 years get bonus) ---
            if paper.year:
                years_old = current_year - paper.year
                if years_old <= 0:
                    recency = 1.0  # Current year
                elif years_old <= 5:
                    recency = 1.0 - (years_old / 5) * 0.5  # 50% decay over 5 years
                else:
                    recency = 0.5 - min(0.5, (years_old - 5) / 20)  # Slower decay after 5 years
            else:
                recency = 0.3  # Unknown year gets neutral score
            recency_scores.append(max(0.0, recency))

        # Normalize each component to 0-1 range
        def normalize_scores(scores: List[float]) -> List[float]:
            if not scores:
                return []
            max_s = max(scores, default=0.0)
            min_s = min(scores, default=0.0)
            span = max_s - min_s
            if span <= 0:
                return [1.0 if max_s > 0 else 0.0] * len(scores)
            return [(s - min_s) / span for s in scores]

        norm_relevance = normalize_scores(relevance_scores)
        norm_citations = normalize_scores(citation_scores)
        norm_recency = normalize_scores(recency_scores)

        # Combine with weights: 50% relevance, 30% citations, 20% recency
        for i, paper in enumerate(papers):
            combined = (
                0.50 * norm_relevance[i] +
                0.30 * norm_citations[i] +
                0.20 * norm_recency[i]
            )
            paper.relevance_score = float(min(1.0, max(0.0, combined)))

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


class SemanticRanker(PaperRanker):
    """
    Combined lexical + semantic ranker using two-stage retrieval.

    Scoring formula:
    - 30% lexical (SimpleRanker: title overlap + citations + recency)
    - 30% bi-encoder similarity (embedding cosine similarity)
    - 40% cross-encoder relevance (precise query-document scoring)

    This provides the best ranking quality by combining:
    1. Fast lexical matching for exact term overlap
    2. Semantic understanding for conceptual similarity
    3. Cross-encoder precision for final ordering
    """

    def __init__(self, config: DiscoveryConfig):
        self.config = config
        self._embedding_service = None
        self._reranker = None
        self._simple_ranker = SimpleRanker(config)

    def _get_embedding_service(self):
        """Lazy load embedding service."""
        if self._embedding_service is None:
            from app.services.embedding_service import get_embedding_service
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def _get_reranker(self):
        """Lazy load reranker."""
        if self._reranker is None:
            from app.services.paper_discovery.reranker import CrossEncoderReranker
            self._reranker = CrossEncoderReranker(self._get_embedding_service())
        return self._reranker

    async def rank(
        self,
        papers: List[DiscoveredPaper],
        query: str,
        target_text: Optional[str] = None,
        target_keywords: Optional[List[str]] = None,
        **kwargs
    ) -> List[DiscoveredPaper]:
        """
        Rank papers using combined lexical + semantic scoring.

        Falls back to SimpleRanker if semantic ranking fails.
        """
        if not papers:
            return []

        # First, get lexical scores using SimpleRanker
        try:
            lexical_ranked = await self._simple_ranker.rank(
                papers, query, target_text, target_keywords, **kwargs
            )
            lexical_scores = {p.get_unique_key(): p.relevance_score for p in lexical_ranked}
        except Exception as e:
            logger.warning(f"[SemanticRanker] Lexical ranking failed: {e}")
            lexical_scores = {p.get_unique_key(): 0.5 for p in papers}

        # Convert papers to dicts for reranker
        paper_dicts = []
        paper_map = {}  # Map back to original papers
        for p in papers:
            paper_id = p.get_unique_key()
            paper_dict = {
                "id": paper_id,
                "doi": p.doi,
                "title": p.title,
                "abstract": p.abstract,
                "lexical_score": lexical_scores.get(paper_id, 0.5)
            }
            paper_dicts.append(paper_dict)
            paper_map[paper_id] = p

        # Try semantic reranking
        try:
            reranker = self._get_reranker()
            reranked = await reranker.rerank(
                query=query,
                papers=paper_dicts,
                top_k_bi_encoder=min(50, len(papers)),
                top_k_final=len(papers),  # Keep all, just reorder
                title_key="title",
                abstract_key="abstract",
                id_key="id"
            )

            # Combine all three signals
            result_papers = []
            for result in reranked:
                paper_id = result.paper.get("id")
                original_paper = paper_map.get(paper_id)

                if original_paper:
                    lexical = result.paper.get("lexical_score", 0.5)

                    # Final weighted score:
                    # 30% lexical + 30% bi-encoder + 40% cross-encoder
                    bi_score = result.bi_encoder_score
                    cross_score_normalized = 1.0 / (1.0 + (2.71828 ** -result.cross_encoder_score))

                    final_score = (
                        0.30 * lexical +
                        0.30 * bi_score +
                        0.40 * cross_score_normalized
                    )

                    original_paper.relevance_score = float(min(1.0, max(0.0, final_score)))
                    result_papers.append(original_paper)

            # Add any papers that weren't in reranker results (shouldn't happen)
            reranked_ids = {r.paper.get("id") for r in reranked}
            for p in papers:
                paper_id = p.get_unique_key()
                if paper_id not in reranked_ids:
                    p.relevance_score = lexical_scores.get(paper_id, 0.0)
                    result_papers.append(p)

            # Sort by final score
            result_papers.sort(key=lambda p: p.relevance_score, reverse=True)

            top_score = result_papers[0].relevance_score if result_papers else 0
            logger.info(
                f"[SemanticRanker] Ranked {len(result_papers)} papers, "
                f"top_score={top_score:.3f}"
            )

            return result_papers

        except Exception as e:
            logger.warning(f"[SemanticRanker] Semantic ranking failed, using lexical only: {e}")
            # Fall back to lexical-only ranking
            return sorted(papers, key=lambda p: lexical_scores.get(p.get_unique_key(), 0), reverse=True)


# ============= Orchestrator Service =============
