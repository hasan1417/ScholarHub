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
        limit: int = 6,
    ) -> List[RetrievalSnippet]:
        snippets: List[RetrievalSnippet] = []
        lowered = query.lower().strip()

        resource_snippets = self._retrieve_from_embeddings(query, context, limit)
        snippets.extend(resource_snippets)

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
                embedding = entry.embedding
                if isinstance(embedding, str):
                    try:
                        embedding = json.loads(embedding)
                    except Exception:  # pragma: no cover
                        continue
                score = _cosine_similarity(query_embedding, embedding)
                resource = resource_map.get(entry.origin_id)
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
                text_lower = entry.text.lower()
                score = sum(text_lower.count(term) for term in lowered if len(term) > 2)
                if score:
                    resource = resource_map.get(entry.origin_id)
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
