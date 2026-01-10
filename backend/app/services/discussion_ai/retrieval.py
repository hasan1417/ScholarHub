from __future__ import annotations

import json
import logging
from math import sqrt
from typing import List, Sequence

from sqlalchemy.orm import Session

from app.models import ProjectDiscussionEmbedding, DiscussionEmbeddingOrigin
from app.services.ai_service import AIService
from app.services.discussion_ai.types import ChannelContext, RetrievalSnippet

logger = logging.getLogger(__name__)


def _cosine_similarity(a: Sequence[float], b: Sequence[float]) -> float:
    sa = sum(x * y for x, y in zip(a, b))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(y * y for y in b))
    return (sa / (na * nb)) if na and nb else 0.0


class DiscussionRetriever:
    """Embedding-backed retrieval for discussion assistant."""

    def __init__(self, db: Session, ai_service: AIService) -> None:
        self.db = db
        self.ai_service = ai_service

    def retrieve(
        self,
        query: str,
        context: ChannelContext,
        *,
        limit: int = 8,  # Increased default limit
    ) -> List[RetrievalSnippet]:
        snippets: List[RetrievalSnippet] = []
        lowered = query.lower().strip()

        # Fetch more candidates for re-ranking
        resource_snippets = self._retrieve_from_embeddings(query, context, limit * 2)

        # Apply smart re-ranking
        if resource_snippets:
            resource_snippets = self._rerank_by_relevance(query, resource_snippets)

        snippets.extend(resource_snippets[:limit])

        # Include most recent messages for conversational continuity
        for idx, message in enumerate(reversed(context.messages[-limit:])):
            score = 0.35
            if lowered and lowered in message.content.lower():
                score = 0.75
            snippets.append(
                RetrievalSnippet(
                    origin="message",
                    origin_id=message.id,
                    content=f"{message.author_name}: {message.content}",
                    score=score - idx * 0.04,
                    metadata={"author_id": str(message.author_id) if message.author_id else None},
                )
            )

        snippets.sort(key=lambda item: item.score, reverse=True)
        return snippets[:limit]

    def _rerank_by_relevance(
        self,
        query: str,
        snippets: List[RetrievalSnippet],
    ) -> List[RetrievalSnippet]:
        """Re-rank snippets based on query relevance signals."""
        if not snippets:
            return snippets

        query_lower = query.lower()
        query_terms = set(query_lower.split())
        # Remove common stopwords for term matching
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
                     "have", "has", "had", "do", "does", "did", "will", "would", "could",
                     "should", "may", "might", "must", "shall", "can", "to", "of", "in",
                     "for", "on", "with", "at", "by", "from", "as", "into", "through",
                     "about", "what", "which", "who", "whom", "this", "that", "these",
                     "those", "am", "or", "and", "but", "if", "because", "until", "while"}
        query_terms = query_terms - stopwords

        for snippet in snippets:
            content_lower = snippet.content.lower()
            original_score = snippet.score

            # Boost for exact phrase match (strongest signal)
            if len(query_lower) > 3 and query_lower in content_lower:
                snippet.score *= 1.5

            # Boost for multiple term matches
            if query_terms:
                term_matches = sum(1 for term in query_terms if len(term) > 2 and term in content_lower)
                if term_matches > 1:
                    snippet.score *= (1 + 0.1 * term_matches)

            # Boost for resource type relevance based on query keywords
            resource_type = snippet.metadata.get("resource_type") if snippet.metadata else None
            if resource_type:
                type_keywords = {
                    "reference": {"reference", "references", "citation", "cite", "paper", "study", "research", "literature"},
                    "paper": {"paper", "draft", "document", "writing", "section"},
                    "meeting": {"meeting", "transcript", "discussion", "sync", "call", "talked", "said"},
                }
                type_matches = type_keywords.get(resource_type, set())
                if type_matches & query_terms:
                    snippet.score *= 1.3

            logger.debug(
                "Re-ranked snippet: original=%.3f, final=%.3f, type=%s",
                original_score,
                snippet.score,
                resource_type,
            )

        return sorted(snippets, key=lambda s: s.score, reverse=True)

    def prewarm(self, contexts: Sequence[ChannelContext]) -> None:
        return None

    def _retrieve_from_embeddings(
        self,
        query: str,
        context: ChannelContext,
        limit: int,
    ) -> List[RetrievalSnippet]:
        resource_map = {resource.id: resource for resource in context.resources}
        entries = (
            self.db.query(ProjectDiscussionEmbedding)
            .filter(
                ProjectDiscussionEmbedding.channel_id == context.channel_id,
                ProjectDiscussionEmbedding.origin_type == DiscussionEmbeddingOrigin.RESOURCE,
                ProjectDiscussionEmbedding.stale.is_(False),
            )
            .all()
        )

        if not entries:
            return []

        query_embedding = None
        if self.ai_service.openai_client:
            try:
                response = self.ai_service.openai_client.embeddings.create(
                    model=self.ai_service.embedding_model,
                    input=query,
                )
                query_embedding = response.data[0].embedding
            except Exception as exc:  # pragma: no cover - external service
                logger.warning("Failed to generate query embedding: %s", exc)

        scored: List[RetrievalSnippet] = []
        if query_embedding:
            for entry in entries:
                resource = resource_map.get(entry.origin_id)
                if resource is None:
                    continue
                embedding = entry.embedding
                if isinstance(embedding, str):
                    try:
                        embedding = json.loads(embedding)
                    except Exception:  # pragma: no cover
                        continue
                score = _cosine_similarity(query_embedding, embedding)
                scored.append(
                    RetrievalSnippet(
                        origin="resource",
                        origin_id=entry.origin_id,
                        content=entry.text,
                        score=score,
                        metadata={
                            "title": resource.title if resource else self._first_line(entry.text),
                            "resource_type": resource.resource_type.value if resource else None,
                        },
                    )
                )
        else:
            lowered = query.lower().split()
            for entry in entries:
                resource = resource_map.get(entry.origin_id)
                if resource is None:
                    continue
                text_lower = entry.text.lower()
                score = sum(text_lower.count(term) for term in lowered if len(term) > 2)
                if score:
                    scored.append(
                        RetrievalSnippet(
                            origin="resource",
                            origin_id=entry.origin_id,
                            content=entry.text,
                            score=float(score),
                            metadata={
                                "title": resource.title if resource else self._first_line(entry.text),
                                "resource_type": resource.resource_type.value if resource else None,
                            },
                        )
                    )

        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:limit]

    @staticmethod
    def _first_line(text: str) -> str:
        return text.splitlines()[0] if text else text
