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
from app.services.discussion_ai.types import AssistantCitation, AssistantReply, AssistantSuggestedAction, SearchResultDigest
from app.models import Reference, DocumentChunk

logger = logging.getLogger(__name__)


class DiscussionAIService:
    """High-level orchestrator for the discussion assistant."""

    # Unified model with dynamic reasoning effort
    MODEL = "gpt-5.2"

    # Reasoning effort levels mapped to query complexity
    # Format: (normal_mode_effort, reasoning_mode_effort)
    EFFORT_MAP = {
        "simple":  ("none", "low"),      # Greetings, short queries
        "normal":  ("low", "medium"),    # Standard research questions
        "complex": ("medium", "high"),   # Create, analyze, compare tasks
    }

    # Simple query patterns - greetings, acknowledgments
    SIMPLE_PATTERNS = {
        "hi", "hey", "hello", "thanks", "thank you", "ok", "okay", "help",
        "what can you do", "who are you", "how are you", "good morning",
        "good afternoon", "good evening", "bye", "goodbye"
    }

    # Complex query keywords - tasks requiring deeper reasoning
    COMPLEX_KEYWORDS = {
        # Creation tasks
        "create", "write", "generate", "draft", "compose", "build", "make",
        # Analysis tasks
        "analyze", "analyse", "evaluate", "assess", "examine", "investigate",
        # Comparison tasks
        "compare", "contrast", "differentiate", "distinguish", "versus", "vs",
        # Review tasks
        "review", "critique", "summarize", "summarise", "synthesize", "synthesise",
        # Explanation tasks
        "explain", "elaborate", "describe in detail", "break down", "walk through",
        # Planning tasks
        "plan", "design", "outline", "structure", "organize", "organise",
        # Research tasks
        "research", "explore", "study", "deep dive", "comprehensive",
    }

    def __init__(
        self,
        db: Session,
        ai_service: AIService,
    ) -> None:
        self.db = db
        self.ai_service = ai_service

        self.context_assembler = ChannelContextAssembler(db)
        self.indexer = ChannelEmbeddingIndexer(db, ai_service)
        self.retriever = DiscussionRetriever(db, ai_service)
        self.prompt_composer = PromptComposer()

    def _classify_query(self, query: str) -> str:
        """Classify query complexity: simple, normal, or complex."""
        q = query.lower().strip()
        words = q.split()

        # Very short queries are simple
        if len(words) <= 2:
            return "simple"

        # Exact match on simple patterns (greetings, etc.)
        if q in self.SIMPLE_PATTERNS:
            return "simple"

        # Check for complex keywords (create, analyze, compare, etc.)
        for keyword in self.COMPLEX_KEYWORDS:
            if keyword in q:
                return "complex"

        # Default to normal
        return "normal"

    def _select_reasoning_effort(self, reasoning: bool, query: str) -> str:
        """Select reasoning effort based on mode and query complexity."""
        complexity = self._classify_query(query)
        effort_pair = self.EFFORT_MAP.get(complexity, ("low", "medium"))

        # Return appropriate effort based on reasoning mode
        return effort_pair[1] if reasoning else effort_pair[0]

    def generate_reply(
        self,
        project: Project,
        channel: ProjectDiscussionChannel,
        question: str,
        *,
        reasoning: bool = False,
        scope: Optional[Sequence[str]] = None,
        recent_search_results: Optional[Sequence[SearchResultDigest]] = None,
    ) -> AssistantReply:
        # Smart routing for non-streaming replies
        # But always use full path if there are recent search results
        complexity = self._classify_query(question)
        has_search_context = recent_search_results and len(recent_search_results) > 0

        # Fast path for simple queries (non-streaming)
        if complexity == "simple" and not reasoning and not has_search_context:
            logger.info("Discussion generate_reply routed to fast path: %s", question[:50])
            effort = self._select_reasoning_effort(reasoning, question)
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
                    model=self.MODEL,
                    reasoning_effort=effort,
                    max_output_tokens=300,
                )
                response_text = self.ai_service.extract_response_text(completion) or "Hello! How can I help?"

            return AssistantReply(
                message=response_text,
                citations=tuple(),
                reasoning_used=False,
                model=self.MODEL,
                usage=None,
                suggested_actions=tuple(),
            )

        # Full path: context assembly + RAG
        resource_scope = self._resolve_resource_scope(scope)
        context = self.context_assembler.build(
            project, channel,
            resource_scope=resource_scope,
            recent_search_results=recent_search_results,
        )
        self.indexer.ensure_resource_embeddings(context)
        snippets = self.retriever.retrieve(question, context)
        metadata_insights = self._maybe_enrich_metadata_only(snippets, question)
        messages = self.prompt_composer.build_messages(question, context, snippets)
        citations = self._build_citations(snippets)

        response_text: str
        reasoning_effort = self._select_reasoning_effort(reasoning, question)
        reasoning_model_used = reasoning  # True if user requested reasoning mode
        usage_meta = None

        if not self.ai_service.openai_client:
            logger.info("AI service not configured; returning mock discussion response")
            response_text = self._mock_response(question, context, snippets)
        else:
            completion = self.ai_service.create_response(
                messages=messages,
                model=self.MODEL,
                reasoning_effort=reasoning_effort,
                max_output_tokens=1000,
            )
            response_text = self.ai_service.extract_response_text(completion) or "I'm sorry, I do not have enough information to help yet."
            usage_meta = self.ai_service.response_usage_to_metadata(getattr(completion, "usage", None))

        message_text, suggested_actions = self._extract_suggested_actions(response_text)
        logger.info(
            "Discussion reply composed: model=%s effort=%s response_len=%d suggested_actions=%d",
            self.MODEL,
            reasoning_effort,
            len(message_text.strip()),
            len(suggested_actions),
        )

        if metadata_insights:
            message_text = f"{message_text}\n\n{metadata_insights}".strip()
        return AssistantReply(
            message=message_text,
            citations=citations,
            reasoning_used=reasoning_model_used,
            model=self.MODEL,
            usage=usage_meta,
            suggested_actions=suggested_actions,
        )

    def _stream_simple(
        self,
        question: str,
        project_title: str,
        reasoning: bool = False,
    ) -> Iterator[dict]:
        """Fast response for simple queries - no RAG, no context building."""
        effort = self._select_reasoning_effort(reasoning, question)
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
                model=self.MODEL,
                reasoning_effort=effort,
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
            reasoning_used=reasoning,
            model=self.MODEL,
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
        recent_search_results: Optional[Sequence[SearchResultDigest]] = None,
    ) -> Iterator[dict]:
        # Smart routing: fast path for simple queries
        # But always use full path if there are recent search results (user might ask about them)
        complexity = self._classify_query(question)
        has_search_context = recent_search_results and len(recent_search_results) > 0

        if complexity == "simple" and not reasoning and not has_search_context:
            logger.info("Discussion query routed to fast path: %s", question[:50])
            yield from self._stream_simple(question, project.title, reasoning)
            return

        # Full path: context assembly + RAG for complex queries
        resource_scope = self._resolve_resource_scope(scope)
        context = self.context_assembler.build(
            project, channel,
            resource_scope=resource_scope,
            recent_search_results=recent_search_results,
        )
        self.indexer.ensure_resource_embeddings(context)
        snippets = self.retriever.retrieve(question, context)
        messages = self.prompt_composer.build_messages(question, context, snippets)
        citations = self._build_citations(snippets)

        reasoning_effort = self._select_reasoning_effort(reasoning, question)
        reasoning_model_used = reasoning  # True if user requested reasoning mode
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
                model=self.MODEL,
                reasoning_effort=reasoning_effort,
                max_output_tokens=1000,
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
                    "Discussion stream returned no text; falling back to non-stream (effort=%s)",
                    reasoning_effort,
                )
                fallback = self.ai_service.create_response(
                    messages=messages,
                    model=self.MODEL,
                    reasoning_effort=reasoning_effort,
                    max_output_tokens=1000,
                )
                response_text = self.ai_service.extract_response_text(fallback)
                usage_meta = self.ai_service.response_usage_to_metadata(getattr(fallback, "usage", None))
                if not response_text.strip():
                    response_text = "I'm sorry, I couldn't retrieve the project objectives right now."
            logger.info(
                "Discussion stream finished: model=%s effort=%s response_len=%d chunks=%d",
                self.MODEL,
                reasoning_effort,
                len(response_text.strip()),
                len(streamed_chunks),
            )

        message_text, suggested_actions = self._extract_suggested_actions(response_text)
        citations = self._filter_citations_by_references(message_text, citations)
        reply = AssistantReply(
            message=message_text,
            citations=citations,
            reasoning_used=reasoning_model_used,
            model=self.MODEL,
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

    # Match both array [...] and single object {...} formats within <actions> tags
    _ACTION_PATTERN = re.compile(r"<actions>\s*(?P<json>[\[\{].*?[\]\}])\s*</actions>", re.DOTALL)

    @staticmethod
    def _extract_json_block(text: str) -> Optional[str]:
        """Extract a JSON array or object from text using bracket counting for nested structures."""
        # Find the start of a JSON array or object that looks like an action
        for i, char in enumerate(text):
            if char not in '[{':
                continue

            # Check if this looks like it could be an action JSON
            remaining = text[i:i+100]
            if '"type"' not in remaining and '"payload"' not in remaining[:500]:
                continue

            # Use bracket counting to find the matching closing bracket
            open_char = char
            close_char = ']' if char == '[' else '}'
            depth = 0
            in_string = False
            escape_next = False

            for j, c in enumerate(text[i:]):
                if escape_next:
                    escape_next = False
                    continue
                if c == '\\' and in_string:
                    escape_next = True
                    continue
                if c == '"' and not escape_next:
                    in_string = not in_string
                    continue
                if in_string:
                    continue

                if c == open_char:
                    depth += 1
                elif c == close_char:
                    depth -= 1
                    if depth == 0:
                        candidate = text[i:i+j+1]
                        # Verify it's valid JSON with action structure
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict) and 'type' in parsed:
                                return candidate
                            elif isinstance(parsed, list) and parsed and isinstance(parsed[0], dict) and 'type' in parsed[0]:
                                return candidate
                        except json.JSONDecodeError:
                            pass
                        break
        return None
    # Fallback pattern for raw JSON action objects (when AI forgets tags)
    _RAW_ACTION_PATTERN = re.compile(r'^\s*\{[^{}]*"type"\s*:\s*"[^"]+_[^"]+"[^{}]*\}\s*$', re.DOTALL)

    def _extract_suggested_actions(self, text: str) -> tuple[str, tuple[AssistantSuggestedAction, ...]]:
        match = self._ACTION_PATTERN.search(text)
        json_block = None
        cleaned_text = text

        if match:
            json_block = match.group('json')
            cleaned_text = text.replace(match.group(0), "").strip()
        else:
            # Fallback: try to find raw JSON action in the text (without <actions> tags)
            # Use bracket matching to handle nested JSON properly
            json_block = self._extract_json_block(text)
            if json_block:
                cleaned_text = text.replace(json_block, "").strip()

        if not json_block:
            return text, tuple()

        actions_data = []
        try:
            parsed = json.loads(json_block)
            if isinstance(parsed, dict):
                actions_data = [parsed]
            elif isinstance(parsed, list):
                actions_data = parsed
        except json.JSONDecodeError as exc:
            logger.warning("Failed to parse assistant action JSON: %s", exc)
            return cleaned_text if cleaned_text else text, tuple()

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

        # If the entire message was just an action, provide a default message
        if not cleaned_text and suggestions:
            cleaned_text = f"I'll help you with that."

        return cleaned_text, tuple(suggestions)
