from __future__ import annotations

import json
import logging
import re
from textwrap import dedent
from typing import Iterator, List, Optional, Sequence

from sqlalchemy.orm import Session

from app.models import Project, ProjectDiscussionChannel, ProjectDiscussionResourceType
from app.services.ai_service import AIService
from app.services.discussion_ai.context import ChannelContextAssembler
from app.services.discussion_ai.prompting import PromptComposer
from app.services.discussion_ai.retrieval import DiscussionRetriever
from app.services.discussion_ai.indexer import ChannelEmbeddingIndexer
from app.services.discussion_ai.types import AssistantCitation, AssistantReply, AssistantSuggestedAction
from app.models import Reference, DocumentChunk

logger = logging.getLogger(__name__)


class DiscussionAIService:
    """High-level orchestrator for the discussion assistant."""

    # Model tiers for smart routing
    FAST_MODEL = "gpt-4o-mini"      # Fast, cheap - for simple queries
    QUALITY_MODEL = "gpt-4o"         # Balanced - for research queries
    REASONING_MODEL = "gpt-5"        # Advanced - when reasoning enabled

    # Simple query patterns that don't need RAG
    SIMPLE_PATTERNS = {
        "hi", "hey", "hello", "thanks", "thank you", "ok", "okay", "help",
        "what can you do", "who are you", "how are you", "good morning",
        "good afternoon", "good evening", "bye", "goodbye"
    }

    def __init__(
        self,
        db: Session,
        ai_service: AIService,
        *,
        default_reasoning_model: str = "gpt-5",
    ) -> None:
        self.db = db
        self.ai_service = ai_service
        self.default_reasoning_model = default_reasoning_model

        self.context_assembler = ChannelContextAssembler(db)
        self.indexer = ChannelEmbeddingIndexer(db, ai_service)
        self.retriever = DiscussionRetriever(db, ai_service)
        self.prompt_composer = PromptComposer()

    def _quick_classify(self, query: str) -> str:
        """Fast classification for query routing - no DB calls needed."""
        q = query.lower().strip()
        words = q.split()

        # Very short queries without research keywords are simple
        if len(words) <= 2:
            return "simple"

        # Exact match on simple patterns
        if q in self.SIMPLE_PATTERNS:
            return "simple"

        # Default to full processing
        return "full"

    def _select_model_smart(self, reasoning: bool, route: str) -> str:
        """Select model based on reasoning mode and query route."""
        if reasoning and self.ai_service.openai_client:
            return self.REASONING_MODEL
        if route == "simple":
            return self.FAST_MODEL
        return self.QUALITY_MODEL

    def generate_reply(
        self,
        project: Project,
        channel: ProjectDiscussionChannel,
        question: str,
        *,
        reasoning: bool = False,
        scope: Optional[Sequence[str]] = None,
    ) -> AssistantReply:
        # Smart routing for non-streaming replies
        route = self._quick_classify(question)

        # Fast path for simple queries (non-streaming)
        if route == "simple" and not reasoning:
            logger.info("Discussion generate_reply routed to fast path: %s", question[:50])
            messages = [
                {
                    "role": "system",
                    "content": f"You are a helpful assistant for the '{project.title}' research project discussion. "
                               "Keep responses brief and friendly."
                },
                {"role": "user", "content": question}
            ]
            if not self.ai_service.openai_client:
                response_text = f"Hello! I'm here to help with the {project.title} project."
            else:
                completion = self.ai_service.create_response(
                    messages=messages,
                    model=self.FAST_MODEL,
                    temperature=0.7,
                    max_output_tokens=300,
                )
                response_text = self.ai_service.extract_response_text(completion) or "Hello! How can I help?"

            return AssistantReply(
                message=response_text,
                citations=tuple(),
                reasoning_used=False,
                model=self.FAST_MODEL,
                usage=None,
                suggested_actions=tuple(),
            )

        # Full path: context assembly + RAG
        resource_scope = self._resolve_resource_scope(scope)
        context = self.context_assembler.build(project, channel, resource_scope=resource_scope)
        self.indexer.ensure_resource_embeddings(context)
        snippets = self.retriever.retrieve(question, context)
        metadata_insights = self._maybe_enrich_metadata_only(snippets, question)
        messages = self.prompt_composer.build_messages(question, context, snippets)
        citations = self._build_citations(snippets)

        response_text: str
        model_name = self._select_model_smart(reasoning, route)
        reasoning_model_used = model_name in (self.REASONING_MODEL, self.default_reasoning_model)
        usage_meta = None

        if not self.ai_service.openai_client:
            logger.info("AI service not configured; returning mock discussion response")
            response_text = self._mock_response(question, context, snippets)
        else:
            completion = self.ai_service.create_response(
                messages=messages,
                model=model_name,
                temperature=0.2,
                max_output_tokens=2000,  # Increased from 900
            )
            response_text = self.ai_service.extract_response_text(completion) or "I'm sorry, I do not have enough information to help yet."
            usage_meta = self.ai_service.response_usage_to_metadata(getattr(completion, "usage", None))

        message_text, suggested_actions = self._extract_suggested_actions(response_text)
        logger.info(
            "Discussion reply composed: response_len=%d suggested_actions=%d citations=%d",
            len(message_text.strip()),
            len(suggested_actions),
            len(citations),
        )

        if metadata_insights:
            message_text = f"{message_text}\n\n{metadata_insights}".strip()
        return AssistantReply(
            message=message_text,
            citations=citations,
            reasoning_used=reasoning_model_used,
            model=model_name,
            usage=usage_meta,
            suggested_actions=suggested_actions,
        )

    def _stream_simple(
        self,
        question: str,
        project_title: str,
    ) -> Iterator[dict]:
        """Fast response for simple queries - no RAG, no context building."""
        messages = [
            {
                "role": "system",
                "content": f"You are a helpful assistant for the '{project_title}' research project discussion. "
                           "Keep responses brief and friendly. You help researchers collaborate and discuss their work."
            },
            {"role": "user", "content": question}
        ]

        response_text = ""
        if not self.ai_service.openai_client:
            response_text = f"Hello! I'm here to help with the {project_title} project. How can I assist you today?"
            yield {"type": "token", "content": response_text}
        else:
            streamed_chunks: list[str] = []
            with self.ai_service.stream_response(
                messages=messages,
                model=self.FAST_MODEL,
                temperature=0.7,
                max_output_tokens=300,
            ) as stream:
                for event in stream:
                    event_type = getattr(event, "type", None)
                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            streamed_chunks.append(delta)
                            yield {"type": "token", "content": delta}
            response_text = "".join(streamed_chunks)

        # Simple queries don't have citations or suggested actions
        reply = AssistantReply(
            message=response_text,
            citations=tuple(),
            reasoning_used=False,
            model=self.FAST_MODEL,
            usage=None,
            suggested_actions=tuple(),
        )
        yield {"type": "result", "reply": reply}

    def stream_reply(
        self,
        project: Project,
        channel: ProjectDiscussionChannel,
        question: str,
        *,
        reasoning: bool = False,
        scope: Optional[Sequence[str]] = None,
    ) -> Iterator[dict]:
        # Smart routing: fast path for simple queries
        route = self._quick_classify(question)

        if route == "simple" and not reasoning:
            logger.info("Discussion query routed to fast path: %s", question[:50])
            yield from self._stream_simple(question, project.title)
            return

        # Full path: context assembly + RAG for complex queries
        resource_scope = self._resolve_resource_scope(scope)
        context = self.context_assembler.build(project, channel, resource_scope=resource_scope)
        self.indexer.ensure_resource_embeddings(context)
        snippets = self.retriever.retrieve(question, context)
        messages = self.prompt_composer.build_messages(question, context, snippets)
        citations = self._build_citations(snippets)

        model_name = self._select_model_smart(reasoning, route)
        reasoning_model_used = model_name in (self.REASONING_MODEL, self.default_reasoning_model)
        usage_meta = None

        if not self.ai_service.openai_client:
            logger.info("AI service not configured; streaming mock response")
            response_text = self._mock_response(question, context, snippets)
            yield {"type": "token", "content": response_text}
        else:
            streamed_chunks: list[str] = []
            final_response = None
            with self.ai_service.stream_response(
                messages=messages,
                model=model_name,
                temperature=0.2,
                max_output_tokens=2000,  # Increased from 900 for detailed responses
            ) as stream:
                for event in stream:
                    event_type = getattr(event, "type", None)
                    if event_type == "response.output_text.delta":
                        delta = getattr(event, "delta", "")
                        if delta:
                            streamed_chunks.append(delta)
                            yield {"type": "token", "content": delta}
                    elif event_type == "error":
                        message = getattr(event, "message", "An unknown streaming error occurred.")
                        raise RuntimeError(f"OpenAI streaming error: {message}")
                    elif event_type == "response.failed":
                        error = getattr(getattr(event, "response", None), "error", None)
                        message = getattr(error, "message", "The response failed to complete.")
                        raise RuntimeError(f"OpenAI response failed: {message}")

                try:
                    final_response = stream.get_final_response()
                except RuntimeError as err:
                    logger.warning("Discussion stream ended without completion: %s", err)

            usage_meta = (
                self.ai_service.response_usage_to_metadata(getattr(final_response, "usage", None))
                if final_response
                else self.ai_service.response_usage_to_metadata(None)
            )
            response_text = self.ai_service.extract_response_text(final_response) if final_response else ""
            if not response_text.strip():
                response_text = "".join(streamed_chunks)
            if not response_text.strip():
                logger.warning(
                    "Discussion stream returned no text; falling back to non-stream completion (model=%s)",
                    model_name,
                )
                fallback = self.ai_service.create_response(
                    messages=messages,
                    model=model_name,
                    max_output_tokens=2000,
                )
                response_text = self.ai_service.extract_response_text(fallback)
                usage_meta = self.ai_service.response_usage_to_metadata(getattr(fallback, "usage", None))
                if not response_text.strip():
                    response_text = "I'm sorry, I couldn't retrieve the project objectives right now."
            logger.info(
                "Discussion stream finished: model=%s response_len=%d chunks=%d final=%s",
                model_name,
                len(response_text.strip()),
                len(streamed_chunks),
                bool(final_response),
            )

        message_text, suggested_actions = self._extract_suggested_actions(response_text)
        citations = self._filter_citations_by_references(message_text, citations)
        reply = AssistantReply(
            message=message_text,
            citations=citations,
            reasoning_used=reasoning_model_used,
            model=model_name,
            usage=usage_meta,
            suggested_actions=suggested_actions,
        )

        yield {"type": "result", "reply": reply}

    def _maybe_enrich_metadata_only(self, snippets, question: str) -> str:
        """If the top snippet comes from a reference without embeddings, request an AI-generated insight."""
        if not snippets:
            return ""

        top = snippets[0]
        if top.origin != "resource":
            return ""

        reference = self.db.query(Reference).filter(Reference.id == top.origin_id).first()
        if not reference:
            return ""

        has_embeddings = any(chunk.embedding is not None for chunk in reference.chunks)
        if has_embeddings:
            return ""

        abstract = reference.abstract or ""
        if not abstract.strip():
            return ""

        metadata_prompt = dedent(
            f"""
            You are summarising a research paper based solely on its metadata.
            Paper title: {reference.title}
            Abstract: {abstract.strip()}

            User question: {question.strip()}

            Provide a concise answer that clearly states you are working from metadata only.
            """
        ).strip()

        try:
            completion = self.ai_service.create_response(
                messages=[
                    {"role": "system", "content": "You are a helpful research assistant."},
                    {"role": "user", "content": metadata_prompt},
                ]
            )
            answer = self.ai_service.extract_response_text(completion)
            if answer:
                return (
                    "**Metadata-only insight:** "
                    + answer.strip()
                    + "\n\nFor deeper analysis, upload the full PDF of this paper to enable document-level reasoning."
                )
        except Exception as exc:  # pragma: no cover - external call
            logger.warning("Metadata enrichment failed for reference %s: %s", reference.id, exc)
        return ""

    def _select_model(self, reasoning: bool) -> str:
        if reasoning and self.ai_service.openai_client:
            return self.default_reasoning_model or self.ai_service.chat_model
        return self.ai_service.chat_model

    def _resolve_resource_scope(
        self,
        scope: Optional[Sequence[str]],
    ) -> Optional[List[ProjectDiscussionResourceType]]:
        if not scope:
            return None
        mapping = {
            "transcripts": ProjectDiscussionResourceType.MEETING,
            "papers": ProjectDiscussionResourceType.PAPER,
            "references": ProjectDiscussionResourceType.REFERENCE,
        }
        resolved: List[ProjectDiscussionResourceType] = []
        for entry in scope:
            if not entry:
                continue
            normalized = entry.strip().lower()
            mapped = mapping.get(normalized)
            if mapped and mapped not in resolved:
                resolved.append(mapped)
        return resolved or None

    def _build_citations(self, snippets) -> tuple[AssistantCitation, ...]:
        citations = []
        seen = set()
        allowed_types = {"paper", "reference", "meeting"}
        for snippet in snippets:
            if snippet.origin != "resource":
                continue
            key = (snippet.origin, snippet.origin_id)
            if key in seen:
                continue
            seen.add(key)
            label = snippet.metadata.get("title") if snippet.metadata else None
            if not label:
                label = f"{snippet.origin.title()} snippet"
            resource_type = snippet.metadata.get("resource_type") if snippet.metadata else None
            if resource_type and resource_type not in allowed_types:
                continue
            citations.append(
                AssistantCitation(
                    origin=snippet.origin,
                    origin_id=snippet.origin_id,
                    label=label,
                    resource_type=resource_type,
                )
            )
        return tuple(citations)

    @staticmethod
    def _filter_citations_by_references(
        message_text: str,
        citations: tuple[AssistantCitation, ...],
    ) -> tuple[AssistantCitation, ...]:
        if not citations or not message_text:
            return citations

        import re

        pattern = re.compile(r"\[(resource|message):([0-9a-fA-F-]+)\]")
        referenced_ids = {
            match.group(2)
            for match in pattern.finditer(message_text)
        }
        if not referenced_ids:
            return tuple()

        filtered = [
            citation
            for citation in citations
            if str(citation.origin_id) in referenced_ids
        ]
        return tuple(filtered)

    @staticmethod
    def _mock_response(question: str, context, snippets) -> str:
        lines = ["[Mock answer] Here's what I know so far:"]
        if context.summary:
            lines.append(f"Channel summary: {context.summary}")
        if snippets:
            lines.append("Relevant snippets:")
            for snippet in snippets[:3]:
                lines.append(f"- {snippet.content}")
        else:
            lines.append("No linked resources yet; try adding a paper or transcript.")
        lines.append("")
        lines.append(f"Question: {question}")
        lines.append("Recommendation: Provide additional context or link a resource for a richer answer.")
        return "\n".join(lines)

    _ACTION_PATTERN = re.compile(r"<actions>\s*(?P<json>\[.*?\])\s*</actions>", re.DOTALL)

    def _extract_suggested_actions(self, text: str) -> tuple[str, tuple[AssistantSuggestedAction, ...]]:
        match = self._ACTION_PATTERN.search(text)
        if not match:
            return text, tuple()

        json_block = match.group('json')
        actions_data = []
        try:
            parsed = json.loads(json_block)
            if isinstance(parsed, dict):
                actions_data = [parsed]
            elif isinstance(parsed, list):
                actions_data = parsed
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse assistant action JSON: %s", exc)
            return text.replace(match.group(0), "").strip(), tuple()

        suggestions: list[AssistantSuggestedAction] = []
        for item in actions_data:
            if not isinstance(item, dict):
                continue
            action_type = str(item.get('type') or item.get('action_type') or '').strip()
            summary = str(item.get('summary') or item.get('title') or '').strip()
            payload = item.get('payload')
            if not action_type or not summary or not isinstance(payload, dict):
                continue
            suggestions.append(
                AssistantSuggestedAction(
                    action_type=action_type,
                    summary=summary,
                    payload=payload,
                )
            )

        cleaned_text = text.replace(match.group(0), "").strip()
        return cleaned_text, tuple(suggestions)
