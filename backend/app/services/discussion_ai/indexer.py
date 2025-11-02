from __future__ import annotations

import hashlib
import json
import logging
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from app.models import ProjectDiscussionEmbedding, DiscussionEmbeddingOrigin
from app.services.ai_service import AIService
from app.services.discussion_ai.types import ChannelContext, ResourceDigest

logger = logging.getLogger(__name__)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


class ChannelEmbeddingIndexer:
    """Ensure discussion resources have up-to-date embeddings."""

    def __init__(self, db: Session, ai_service: AIService) -> None:
        self.db = db
        self.ai_service = ai_service

    def ensure_resource_embeddings(self, context: ChannelContext) -> None:
        if not self.ai_service.openai_client:
            logger.debug("AI service not configured; skipping embedding indexing")
            return

        for resource in context.resources:
            text = self._build_resource_text(resource)
            if not text:
                continue
            signature = _hash_text(text)
            origin_type = DiscussionEmbeddingOrigin.RESOURCE

            entry: Optional[ProjectDiscussionEmbedding] = (
                self.db.query(ProjectDiscussionEmbedding)
                .filter(
                    ProjectDiscussionEmbedding.origin_type == origin_type,
                    ProjectDiscussionEmbedding.origin_id == resource.id,
                )
                .first()
            )

            if entry and entry.text_signature == signature and not entry.stale:
                continue

            try:
                embedding_response = self.ai_service.openai_client.embeddings.create(
                    model=self.ai_service.embedding_model,
                    input=text,
                )
            except Exception as exc:  # pragma: no cover - external service
                logger.warning("Failed to embed discussion resource %s: %s", resource.id, exc)
                continue

            embedding_vector = embedding_response.data[0].embedding

            if entry is None:
                entry = ProjectDiscussionEmbedding(
                    project_id=context.project_id,
                    channel_id=context.channel_id,
                    origin_type=origin_type,
                    origin_id=resource.id,
                    text=text,
                    text_signature=signature,
                    embedding=embedding_vector,
                )
                self.db.add(entry)
            else:
                entry.text = text
                entry.text_signature = signature
                entry.embedding = embedding_vector
                entry.stale = False

        self.db.flush()
        self.db.commit()

    @staticmethod
    def _build_resource_text(resource: ResourceDigest) -> str:
        parts: list[str] = [resource.title]
        if resource.summary:
            parts.append(resource.summary)
        if resource.metadata:
            parts.append(" | ".join(resource.metadata))
        return "\n".join(part for part in parts if part).strip()

    def mark_resources_stale(self, resource_ids: Iterable[str]) -> None:
        self.db.query(ProjectDiscussionEmbedding).filter(
            ProjectDiscussionEmbedding.origin_type == DiscussionEmbeddingOrigin.RESOURCE,
            ProjectDiscussionEmbedding.origin_id.in_(resource_ids),
        ).update({"stale": True}, synchronize_session=False)
