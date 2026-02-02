"""
Two-Stage Reranker for Semantic Search

Stage 1 (Bi-encoder): Fast embedding-based similarity filtering
Stage 2 (Cross-encoder): Precise relevance scoring for top candidates

This achieves the best relevance quality while keeping latency reasonable.
"""

from __future__ import annotations

import asyncio
import logging
import math
from dataclasses import dataclass
from typing import List, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass
class RerankedResult:
    """Result from two-stage reranking."""
    paper: Dict[str, Any]
    bi_encoder_score: float
    cross_encoder_score: float
    final_score: float


class CrossEncoderReranker:
    """
    Two-stage retrieval with cross-encoder reranking.

    Stage 1 (Bi-encoder):
    - Embed query and paper titles/abstracts
    - Compute cosine similarity
    - Keep top K candidates (fast filtering)

    Stage 2 (Cross-encoder):
    - Score query-document pairs directly
    - More accurate but slower
    - Final relevance ordering

    Models used:
    - Bi-encoder: all-MiniLM-L6-v2 (via EmbeddingService)
    - Cross-encoder: cross-encoder/ms-marco-MiniLM-L-6-v2

    Final score formula:
    - 40% bi-encoder similarity
    - 60% cross-encoder relevance
    """

    # Cross-encoder model
    # Options:
    # - "cross-encoder/ms-marco-MiniLM-L-6-v2" (fast, good quality)
    # - "BAAI/bge-reranker-base" (better quality, slower)
    # - "BAAI/bge-reranker-large" (best quality, slowest)
    CROSS_ENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self, embedding_service: "EmbeddingService"):
        """
        Initialize the reranker.

        Args:
            embedding_service: EmbeddingService instance for bi-encoder embeddings
        """
        self.embedding_service = embedding_service
        self._cross_encoder = None
        self._lock = asyncio.Lock()

    def _load_cross_encoder(self):
        """Lazy load the cross-encoder model."""
        if self._cross_encoder is None:
            from sentence_transformers import CrossEncoder
            logger.info(f"[Reranker] Loading cross-encoder: {self.CROSS_ENCODER_MODEL}")
            self._cross_encoder = CrossEncoder(self.CROSS_ENCODER_MODEL)
            logger.info("[Reranker] Cross-encoder loaded")
        return self._cross_encoder

    async def rerank(
        self,
        query: str,
        papers: List[Dict[str, Any]],
        top_k_bi_encoder: int = 50,
        top_k_final: int = 20,
        title_key: str = "title",
        abstract_key: str = "abstract",
        id_key: str = "id"
    ) -> List[RerankedResult]:
        """
        Two-stage reranking pipeline.

        Args:
            query: Search query string
            papers: List of paper dicts with title, abstract, and id
            top_k_bi_encoder: Number of candidates to keep after bi-encoder stage
            top_k_final: Number of results to return after cross-encoder stage
            title_key: Key for paper title in dict
            abstract_key: Key for paper abstract in dict
            id_key: Key for paper identifier in dict

        Returns:
            List of RerankedResult ordered by final_score descending
        """
        if not papers:
            return []

        if not query or not query.strip():
            logger.warning("[Reranker] Empty query, returning papers unchanged")
            return [
                RerankedResult(paper=p, bi_encoder_score=0.0, cross_encoder_score=0.0, final_score=0.0)
                for p in papers[:top_k_final]
            ]

        logger.info(f"[Reranker] START query='{query[:50]}...' papers={len(papers)}")

        # Stage 1: Bi-encoder filtering
        bi_encoder_results = await self._bi_encoder_stage(
            query=query,
            papers=papers,
            top_k=top_k_bi_encoder,
            title_key=title_key,
            abstract_key=abstract_key
        )

        if not bi_encoder_results:
            logger.warning("[Reranker] No bi-encoder results")
            return []

        # Stage 2: Cross-encoder reranking
        final_results = await self._cross_encoder_stage(
            query=query,
            candidates=bi_encoder_results,
            top_k=top_k_final,
            title_key=title_key,
            abstract_key=abstract_key
        )

        top_score = final_results[0].final_score if final_results else 0
        logger.info(
            f"[Reranker] COMPLETE results={len(final_results)} "
            f"top_score={top_score:.3f}"
        )

        return final_results

    async def _bi_encoder_stage(
        self,
        query: str,
        papers: List[Dict[str, Any]],
        top_k: int,
        title_key: str,
        abstract_key: str
    ) -> List[tuple]:
        """
        Stage 1: Bi-encoder similarity filtering.

        Returns list of (paper, bi_score) tuples sorted by score descending.
        """
        # Embed query
        query_embedding = await self.embedding_service.embed(query)

        # Embed papers
        paper_embeddings = await self.embedding_service.embed_papers(
            papers,
            title_key=title_key,
            abstract_key=abstract_key
        )

        # Compute similarities
        # Key must match embed_papers logic: doi > id > paper_id
        scored_papers = []
        for paper in papers:
            paper_id = paper.get("doi") or paper.get("id") or paper.get("paper_id")
            paper_id = str(paper_id) if paper_id else paper.get(title_key, "")
            embedding = paper_embeddings.get(paper_id)

            if embedding:
                similarity = self.embedding_service.cosine_similarity(query_embedding, embedding)
            else:
                similarity = 0.0

            scored_papers.append((paper, similarity))

        # Sort by similarity and keep top K
        scored_papers.sort(key=lambda x: x[1], reverse=True)
        return scored_papers[:top_k]

    async def _cross_encoder_stage(
        self,
        query: str,
        candidates: List[tuple],
        top_k: int,
        title_key: str,
        abstract_key: str
    ) -> List[RerankedResult]:
        """
        Stage 2: Cross-encoder reranking.

        Takes candidates from bi-encoder stage and scores with cross-encoder.
        """
        if not candidates:
            return []

        # Prepare query-document pairs for cross-encoder
        pairs = []
        for paper, _ in candidates:
            title = paper.get(title_key, "")
            abstract = paper.get(abstract_key, "") or ""
            # Truncate to avoid token limits
            doc_text = f"{title}. {abstract[:500]}"
            pairs.append([query, doc_text])

        # Score with cross-encoder (run in thread pool)
        async with self._lock:
            cross_encoder = self._load_cross_encoder()
            loop = asyncio.get_event_loop()
            cross_scores = await loop.run_in_executor(
                None,
                lambda: cross_encoder.predict(pairs)
            )

        # Combine scores and create results
        results = []
        for (paper, bi_score), cross_score in zip(candidates, cross_scores):
            # Normalize cross-encoder score to [0, 1]
            # ms-marco model outputs logits typically in [-10, 10] range
            normalized_cross = self._sigmoid(float(cross_score))

            # Final weighted score: 40% bi-encoder, 60% cross-encoder
            final_score = 0.40 * bi_score + 0.60 * normalized_cross

            results.append(RerankedResult(
                paper=paper,
                bi_encoder_score=bi_score,
                cross_encoder_score=float(cross_score),
                final_score=final_score
            ))

        # Sort by final score
        results.sort(key=lambda r: r.final_score, reverse=True)
        return results[:top_k]

    @staticmethod
    def _sigmoid(x: float) -> float:
        """Sigmoid function for normalizing cross-encoder scores."""
        return 1.0 / (1.0 + math.exp(-x))


class BiEncoderOnlyReranker:
    """
    Simpler reranker using only bi-encoder embeddings.

    Use this when:
    - Cross-encoder latency is unacceptable
    - Results don't need highest precision
    - Running on resource-constrained systems
    """

    def __init__(self, embedding_service: "EmbeddingService"):
        self.embedding_service = embedding_service

    async def rerank(
        self,
        query: str,
        papers: List[Dict[str, Any]],
        top_k: int = 20,
        title_key: str = "title",
        abstract_key: str = "abstract"
    ) -> List[RerankedResult]:
        """
        Single-stage bi-encoder reranking.

        Returns papers ranked by embedding similarity to query.
        """
        if not papers or not query:
            return []

        # Embed query
        query_embedding = await self.embedding_service.embed(query)

        # Embed papers
        paper_embeddings = await self.embedding_service.embed_papers(
            papers,
            title_key=title_key,
            abstract_key=abstract_key
        )

        # Score and rank
        results = []
        for paper in papers:
            paper_id = str(paper.get("doi") or paper.get(title_key, ""))
            embedding = paper_embeddings.get(paper_id)

            if embedding:
                score = self.embedding_service.cosine_similarity(query_embedding, embedding)
            else:
                score = 0.0

            results.append(RerankedResult(
                paper=paper,
                bi_encoder_score=score,
                cross_encoder_score=0.0,
                final_score=score
            ))

        results.sort(key=lambda r: r.final_score, reverse=True)
        return results[:top_k]
