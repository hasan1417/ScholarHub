"""Preload the semantic-search models at container startup.

Without this, the FIRST user-triggered paper search in a process pays the
full cold-start cost:

    - all-MiniLM-L6-v2 bi-encoder ~1-2s
    - ms-marco-MiniLM-L-6-v2 cross-encoder ~10-15s

Both models are already module-level cached after first load, so we just
need to trigger that first load ourselves, off the request path.
"""
from __future__ import annotations

import asyncio
import logging
import time

logger = logging.getLogger(__name__)


def _warmup_bi_encoder() -> None:
    """Trigger a bi-encoder load by embedding a trivial sentence."""
    try:
        from app.services.embedding_service import SentenceTransformerProvider
        provider = SentenceTransformerProvider()
        # Internal lazy-load path; running a tiny encode forces the download/import.
        model = provider._load_model()
        # One tiny encode so the inference graph is compiled too.
        model.encode("warmup", normalize_embeddings=True)
        logger.info("[SemanticWarmup] Bi-encoder ready")
    except Exception as exc:
        logger.warning(f"[SemanticWarmup] Bi-encoder warmup failed: {exc}")


def _warmup_cross_encoder() -> None:
    """Trigger a cross-encoder load by scoring one trivial pair."""
    try:
        from app.services.paper_discovery.reranker import CrossEncoderReranker
        from app.services.embedding_service import EmbeddingService
        reranker = CrossEncoderReranker(EmbeddingService())
        model = reranker._load_cross_encoder()
        # Force a single predict so the model is JIT-compiled.
        model.predict([("warmup query", "warmup document")])
        logger.info("[SemanticWarmup] Cross-encoder ready")
    except Exception as exc:
        logger.warning(f"[SemanticWarmup] Cross-encoder warmup failed: {exc}")


def _check_semantic_scholar_key() -> None:
    """One tiny probe to validate SEMANTIC_SCHOLAR_API_KEY at boot.

    The goal is visibility: a rejected key previously only showed up as
    degraded source stats in the UI. This surfaces the problem in the
    container boot log where an operator actually reads it.
    """
    try:
        from app.core.config import settings
        key = settings.SEMANTIC_SCHOLAR_API_KEY
        if not key:
            logger.info("[SemanticScholar] No API key configured — searches will use the public rate-limited endpoint")
            return
        import httpx
        resp = httpx.get(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": "warmup", "limit": 1, "fields": "title"},
            headers={"x-api-key": key, "User-Agent": "ScholarHub/1.0"},
            timeout=10,
        )
        if resp.status_code == 200:
            logger.info("[SemanticScholar] API key live")
        elif resp.status_code == 403:
            logger.warning(
                "[SemanticScholar] API key rejected (403). Possible causes: "
                "(a) newly-approved key still propagating (wait ~24h), "
                "(b) key revoked, or (c) wrong key copied into the env. "
                "This source will return empty results until the key works."
            )
        elif resp.status_code == 429:
            # No key case shouldn't hit this branch, but a key can still 429
            # if we exceed the 1 req/s limit during burst fan-out.
            logger.info("[SemanticScholar] API key rate-limited at startup (will still work under quota)")
        else:
            logger.warning(
                "[SemanticScholar] API key check returned HTTP %s: %s",
                resp.status_code, resp.text[:200],
            )
    except Exception as exc:
        logger.warning(f"[SemanticScholar] API key check failed (network?): {exc}")


async def warmup_semantic_models() -> None:
    """Load bi-encoder + cross-encoder in a worker thread so we don't block the event loop."""
    t0 = time.monotonic()
    logger.info("[SemanticWarmup] Preloading bi-encoder and cross-encoder…")
    # Run all three in threads so startup stays responsive. The S2 key check
    # is piggy-backed here so everything that warms the search path lives
    # in one spot.
    await asyncio.gather(
        asyncio.to_thread(_warmup_bi_encoder),
        asyncio.to_thread(_warmup_cross_encoder),
        asyncio.to_thread(_check_semantic_scholar_key),
    )
    elapsed = time.monotonic() - t0
    logger.info(f"[SemanticWarmup] Done in {elapsed:.1f}s — first search will skip cold-start")
