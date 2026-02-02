"""
Unified Embedding Service for Semantic Search

Provides embedding generation with multiple provider support:
- SentenceTransformers (local, free, fast)
- OpenAI (API, higher quality)

Used by:
- Search reranking (semantic similarity)
- Library semantic search (pgvector)
- Discussion context matching
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
import hashlib
import logging
import asyncio

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """Abstract base class for embedding providers."""

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Model identifier string."""
        ...

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Embedding vector dimensions."""
        ...

    @abstractmethod
    async def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        ...

    @abstractmethod
    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        ...


class SentenceTransformerProvider(EmbeddingProvider):
    """
    Local embeddings via sentence-transformers.

    Model: all-MiniLM-L6-v2
    - Dimensions: 384
    - Speed: ~50ms per text (CPU)
    - Quality: Good for semantic similarity
    - Cost: Free (runs locally)
    """

    MODEL = "all-MiniLM-L6-v2"
    DIMENSIONS = 384

    def __init__(self):
        self._model = None
        self._lock = asyncio.Lock()

    def _load_model(self):
        """Lazy load the model on first use."""
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            logger.info(f"[EmbeddingService] Loading SentenceTransformer model: {self.MODEL}")
            self._model = SentenceTransformer(self.MODEL)
            logger.info(f"[EmbeddingService] Model loaded successfully")
        return self._model

    @property
    def model_name(self) -> str:
        return self.MODEL

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        async with self._lock:
            model = self._load_model()
            loop = asyncio.get_event_loop()
            embedding = await loop.run_in_executor(
                None,
                lambda: model.encode(text, normalize_embeddings=True)
            )
            return embedding.tolist()

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in batch."""
        if not texts:
            return []

        async with self._lock:
            model = self._load_model()
            loop = asyncio.get_event_loop()
            embeddings = await loop.run_in_executor(
                None,
                lambda: model.encode(texts, normalize_embeddings=True, batch_size=32)
            )
            return embeddings.tolist()


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """
    OpenAI embeddings via API.

    Model: text-embedding-3-small
    - Dimensions: 1536
    - Speed: ~100ms per batch (network)
    - Quality: Excellent
    - Cost: $0.02 per 1M tokens
    """

    MODEL = "text-embedding-3-small"
    DIMENSIONS = 1536

    def __init__(self, api_key: str):
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(api_key=api_key)

    @property
    def model_name(self) -> str:
        return self.MODEL

    @property
    def dimensions(self) -> int:
        return self.DIMENSIONS

    async def embed(self, text: str) -> List[float]:
        """Generate embedding for a single text."""
        response = await self._client.embeddings.create(
            model=self.MODEL,
            input=text
        )
        return response.data[0].embedding

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts."""
        if not texts:
            return []

        # OpenAI supports up to 2048 texts per batch
        response = await self._client.embeddings.create(
            model=self.MODEL,
            input=texts
        )
        return [item.embedding for item in response.data]


class EmbeddingService:
    """
    Unified embedding service with caching and provider abstraction.

    Features:
    - Multiple provider support (local + API)
    - Content hashing for deduplication
    - Batch processing for efficiency
    - Memory cache for repeated queries
    """

    # In-memory LRU cache size
    CACHE_SIZE = 1000

    def __init__(
        self,
        provider: Optional[EmbeddingProvider] = None,
        use_cache: bool = True
    ):
        """
        Initialize embedding service.

        Args:
            provider: Embedding provider instance. Defaults to SentenceTransformer.
            use_cache: Whether to use in-memory LRU cache.
        """
        self.provider = provider or SentenceTransformerProvider()
        self.use_cache = use_cache
        self._cache: Dict[str, List[float]] = {}

        logger.info(
            f"[EmbeddingService] Initialized with provider={self.provider.model_name}, "
            f"dims={self.provider.dimensions}, cache={use_cache}"
        )

    @property
    def model_name(self) -> str:
        return self.provider.model_name

    @property
    def dimensions(self) -> int:
        return self.provider.dimensions

    @staticmethod
    def content_hash(text: str) -> str:
        """Generate SHA-256 hash for content deduplication."""
        normalized = text.strip().lower()
        return hashlib.sha256(normalized.encode('utf-8')).hexdigest()

    @staticmethod
    def prepare_paper_text(
        title: str,
        abstract: Optional[str] = None,
        max_abstract_len: int = 2000
    ) -> str:
        """
        Prepare paper text for embedding.

        Format: "Title: {title}\nAbstract: {abstract}"
        Truncates abstract to prevent token overflow.
        """
        parts = [f"Title: {title}"]
        if abstract:
            truncated = abstract[:max_abstract_len]
            if len(abstract) > max_abstract_len:
                truncated = truncated.rsplit(' ', 1)[0] + "..."
            parts.append(f"Abstract: {truncated}")
        return "\n".join(parts)

    async def embed(self, text: str) -> List[float]:
        """
        Generate embedding for text, using cache if available.
        """
        if not text or not text.strip():
            raise ValueError("Cannot embed empty text")

        # Check cache
        if self.use_cache:
            cache_key = self.content_hash(text)
            if cache_key in self._cache:
                return self._cache[cache_key]

        # Generate embedding
        embedding = await self.provider.embed(text)

        # Update cache
        if self.use_cache:
            if len(self._cache) >= self.CACHE_SIZE:
                # Simple cache eviction: remove oldest entries
                keys_to_remove = list(self._cache.keys())[:self.CACHE_SIZE // 4]
                for k in keys_to_remove:
                    del self._cache[k]
            self._cache[cache_key] = embedding

        return embedding

    async def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts.

        Uses cache for already-embedded texts and batches the rest.
        """
        if not texts:
            return []

        results: List[Optional[List[float]]] = [None] * len(texts)
        to_embed_indices: List[int] = []
        to_embed_texts: List[str] = []

        # Check cache for each text
        for i, text in enumerate(texts):
            if not text or not text.strip():
                results[i] = [0.0] * self.dimensions  # Zero vector for empty text
                continue

            cache_key = self.content_hash(text)
            if self.use_cache and cache_key in self._cache:
                results[i] = self._cache[cache_key]
                continue

            to_embed_indices.append(i)
            to_embed_texts.append(text)

        # Batch embed uncached texts
        if to_embed_texts:
            embeddings = await self.provider.embed_batch(to_embed_texts)

            for idx, orig_idx in enumerate(to_embed_indices):
                embedding = embeddings[idx]
                results[orig_idx] = embedding

                # Update cache
                if self.use_cache and len(self._cache) < self.CACHE_SIZE:
                    text = to_embed_texts[idx]
                    cache_key = self.content_hash(text)
                    self._cache[cache_key] = embedding

        # Convert to non-optional list (all None should be filled)
        return [r if r is not None else [0.0] * self.dimensions for r in results]

    async def embed_papers(
        self,
        papers: List[Dict[str, Any]],
        title_key: str = "title",
        abstract_key: str = "abstract"
    ) -> Dict[str, List[float]]:
        """
        Embed multiple papers, returning a dict mapping paper ID to embedding.

        Args:
            papers: List of paper dicts with title, abstract, and id/doi
            title_key: Key for title in paper dict
            abstract_key: Key for abstract in paper dict

        Returns:
            Dict mapping paper identifier to embedding vector
        """
        texts = []
        ids = []

        for paper in papers:
            title = paper.get(title_key, "")
            abstract = paper.get(abstract_key)
            text = self.prepare_paper_text(title, abstract)
            texts.append(text)

            # Use DOI if available, otherwise id, then fallback to title
            paper_id = paper.get("doi") or paper.get("id") or paper.get("paper_id")
            paper_id_str = str(paper_id) if paper_id else title
            ids.append(paper_id_str if paper_id_str else str(len(ids)))

        embeddings = await self.embed_batch(texts)

        return {pid: emb for pid, emb in zip(ids, embeddings)}

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        a_arr = np.array(a)
        b_arr = np.array(b)

        dot_product = np.dot(a_arr, b_arr)
        norm_a = np.linalg.norm(a_arr)
        norm_b = np.linalg.norm(b_arr)

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return float(dot_product / (norm_a * norm_b))

    def clear_cache(self):
        """Clear the in-memory cache."""
        self._cache.clear()
        logger.info("[EmbeddingService] Cache cleared")


# Singleton instance for reuse across the application
_default_service: Optional[EmbeddingService] = None

# Required dimensions for persisted embeddings (pgvector column is VECTOR(384))
PERSISTED_EMBEDDING_DIMENSIONS = 384


def get_embedding_service() -> EmbeddingService:
    """
    Get or create the default embedding service instance.

    Uses SentenceTransformers (384 dims) - compatible with persisted embeddings.
    """
    global _default_service
    if _default_service is None:
        _default_service = EmbeddingService()
    return _default_service


def get_embedding_service_for_persistence() -> EmbeddingService:
    """
    Get embedding service for persisted embeddings (library storage).

    IMPORTANT: Always uses SentenceTransformers (384 dims) to match
    the paper_embeddings.embedding VECTOR(384) column.

    Do NOT use OpenAI provider here - dimension mismatch will cause errors.
    """
    return get_embedding_service()  # Always returns 384-dim provider


def get_embedding_service_with_openai(api_key: str) -> EmbeddingService:
    """
    Create an embedding service using OpenAI provider.

    WARNING: This returns 1536-dim embeddings. Only use for ephemeral
    operations (e.g., search-time reranking). Do NOT use for persisted
    embeddings stored in paper_embeddings table.
    """
    provider = OpenAIEmbeddingProvider(api_key)
    return EmbeddingService(provider=provider)


def validate_embedding_dimensions(embedding: List[float], for_persistence: bool = False) -> bool:
    """
    Validate embedding dimensions.

    Args:
        embedding: The embedding vector to validate
        for_persistence: If True, validates against PERSISTED_EMBEDDING_DIMENSIONS

    Returns:
        True if valid, False otherwise
    """
    if for_persistence:
        return len(embedding) == PERSISTED_EMBEDDING_DIMENSIONS
    return len(embedding) > 0
