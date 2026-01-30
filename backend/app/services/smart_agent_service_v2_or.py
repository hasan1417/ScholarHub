"""
Smart Agent Service V2 OR - OpenRouter version for LaTeX Editor AI.

Simple approach:
- Templates are in the system prompt (authoritative)
- AI uses propose_edit directly for conversions
- Single API call for most operations
"""
import os
import re
import json
import logging
from typing import Optional, Generator, List, Dict, Any
from sqlalchemy.orm import Session
from openai import OpenAI

from app.services.smart_agent_service_v2 import (
    EDITOR_TOOLS,
    SYSTEM_PROMPT,
    _resolve_paper_id,
)
from app.services.discussion_ai.openrouter_orchestrator import model_supports_reasoning
from app.constants.paper_templates import CONFERENCE_TEMPLATES

logger = logging.getLogger(__name__)


# Tool for searching attached references (RAG)
SEARCH_REFERENCES_TOOL = {
    "type": "function",
    "function": {
        "name": "search_references",
        "description": "Search the attached references for specific information using semantic search.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "What information are you looking for?"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Maximum results (default: 10)",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    }
}


class SmartAgentServiceV2OR:
    """
    OpenRouter-powered LaTeX Editor AI.

    Simple approach:
    - Templates are in the system prompt (authoritative)
    - AI uses propose_edit directly for conversions
    - Single API call for most operations
    """

    def __init__(self, model: str = "openai/gpt-5.2-20251211", user_api_key: Optional[str] = None):
        self.model = model

        api_key = user_api_key or os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            logger.warning("No OpenRouter API key available")
            self.client = None
        else:
            self.client = OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://scholarhub.space",
                    "X-Title": "ScholarHub LaTeX Editor"
                }
            )

        self._db = None
        self._user_id = None
        self._paper_id = None

    def _add_line_numbers(self, text: str) -> str:
        """Add line numbers to text."""
        lines = text.split('\n')
        width = max(len(str(len(lines))), 3)
        numbered = [f"{i:>{width}}| {line}" for i, line in enumerate(lines, 1)]
        return '\n'.join(numbered)

    def stream_query(
        self,
        db: Session,
        user_id: str,
        query: str,
        paper_id: Optional[str] = None,
        document_excerpt: Optional[str] = None,
        reasoning_mode: bool = False,
    ) -> Generator[str, None, None]:
        """Stream response using OpenRouter."""

        if not self.client:
            yield "OpenRouter API key not configured."
            return

        # Store for reference search tool
        self._db = db
        self._user_id = user_id
        self._paper_id = paper_id

        # Get reference context
        ref_context = self._get_reference_context(db, user_id, paper_id, query)

        # Build context with line numbers
        context_parts = []
        doc_size = len(document_excerpt or "")

        if document_excerpt:
            numbered_doc = self._add_line_numbers(document_excerpt)
            context_parts.append(f"=== DOCUMENT ({doc_size:,} chars) ===\n{numbered_doc}")

        if ref_context:
            context_parts.append(f"=== ATTACHED REFERENCES ===\n{ref_context}")

        full_context = "\n\n".join(context_parts) if context_parts else "No document provided."

        use_reasoning = reasoning_mode and model_supports_reasoning(self.model)

        logger.info(f"[SmartAgentV2OR] model={self.model}, reasoning={use_reasoning}, doc_size={doc_size}")

        # Build tools list (add reference search)
        tools = list(EDITOR_TOOLS) + [SEARCH_REFERENCES_TOOL]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"{full_context}\n\n---\n\nUser request: {query}"}
        ]

        try:
            # Multi-turn for reference searches only
            max_turns = 3
            turn = 0

            while turn < max_turns:
                turn += 1

                request_kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": "required" if turn == 1 else "auto",
                    "max_tokens": 4000,
                }

                if use_reasoning:
                    request_kwargs["extra_body"] = {"reasoning_effort": "high"}

                response = self.client.chat.completions.create(**request_kwargs)
                choice = response.choices[0]

                if choice.message.tool_calls:
                    tool_call = choice.message.tool_calls[0]
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    logger.info(f"[SmartAgentV2OR] Turn {turn}: {tool_name}")

                    # Intermediate tools - return info to AI for further processing
                    if tool_name == "search_references":
                        search_query = tool_args.get("query", "")
                        max_results = tool_args.get("max_results", 10)
                        search_results = self._search_references_for_tool(search_query, max_results)

                        messages.append(choice.message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": search_results
                        })
                        continue  # Let AI process results

                    elif tool_name == "apply_template":
                        template_info = "".join(self._handle_apply_template(tool_args.get("template_id", "")))
                        messages.append(choice.message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": template_info
                        })
                        continue  # AI will call propose_edit next

                    # All other tools - format and return
                    yield from self._format_tool_response(tool_name, tool_args)
                    return

                elif choice.message.content:
                    yield choice.message.content
                    return

            yield "Could not complete the request. Please try again."

        except Exception as e:
            logger.error(f"[SmartAgentV2OR] Error: {e}")
            yield f"Sorry, an error occurred: {str(e)}"

    def _format_tool_response(self, tool_name: str, args: dict) -> Generator[str, None, None]:
        """Format the tool response for the frontend."""

        if tool_name == "answer_question":
            yield args.get("answer", "")

        elif tool_name == "propose_edit":
            explanation = args.get("explanation", "")
            edits = args.get("edits", [])

            yield f"{explanation}\n\n"

            for edit in edits:
                yield "<<<EDIT>>>\n"
                yield f"{edit.get('description', 'Edit')}\n"
                yield "<<<LINES>>>\n"
                yield f"{edit.get('start_line', 1)}-{edit.get('end_line', 1)}\n"
                yield "<<<ANCHOR>>>\n"
                yield f"{edit.get('anchor', '')}\n"
                yield "<<<PROPOSED>>>\n"
                yield f"{edit.get('proposed', '')}\n"
                yield "<<<END>>>\n\n"

        elif tool_name == "review_document":
            summary = args.get("summary", "")
            strengths = args.get("strengths", [])
            improvements = args.get("improvements", [])
            offer_edits = args.get("offer_edits", True)

            yield f"## Review\n\n{summary}\n\n"

            if strengths:
                yield "### Strengths\n"
                for s in strengths:
                    yield f"- {s}\n"
                yield "\n"

            if improvements:
                yield "### Suggested Improvements\n"
                for i in improvements:
                    yield f"- {i}\n"
                yield "\n"

            if offer_edits:
                yield "Would you like me to make any of these suggested changes?"

        elif tool_name == "explain_references":
            yield args.get("explanation", "")
            if args.get("suggest_discovery"):
                yield "\n\nTo discover new papers, use the **Discussion AI** or **Discovery page**."

        elif tool_name == "list_available_templates":
            yield from self._handle_list_templates()

        else:
            yield f"Unknown tool: {tool_name}"

    def _get_reference_context(
        self,
        db: Session,
        user_id: str,
        paper_id: Optional[str],
        query: str,
        max_refs: int = 25
    ) -> str:
        """Get reference summaries for context."""
        try:
            from app.models.reference import Reference
            from app.models.paper_reference import PaperReference

            if not paper_id:
                return ""

            resolved_id = _resolve_paper_id(db, paper_id)
            if not resolved_id:
                return "Paper not found."

            refs = db.query(Reference).join(
                PaperReference, PaperReference.reference_id == Reference.id
            ).filter(
                PaperReference.paper_id == resolved_id
            ).limit(max_refs).all()

            if not refs:
                return "No references attached to this paper."

            lines = [f"({len(refs)} references attached):\n"]
            for i, ref in enumerate(refs, 1):
                authors = ", ".join(ref.authors[:2]) + (" et al." if len(ref.authors) > 2 else "") if ref.authors else "Unknown"
                lines.append(f"{i}. {ref.title} ({authors}, {ref.year or 'n.d.'})")
                if ref.abstract:
                    lines.append(f"   Abstract: {ref.abstract[:200]}...")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error getting reference context: {e}")
            return ""

    def _search_references_for_tool(self, query: str, max_results: int = 10) -> str:
        """Search references for the AI tool call using semantic search."""
        try:
            from app.models.reference import Reference
            from app.models.paper_reference import PaperReference
            from app.models.document_chunk import DocumentChunk

            if not self._paper_id:
                return "No paper ID available for reference search."

            resolved_id = _resolve_paper_id(self._db, self._paper_id)
            if not resolved_id:
                return "Paper not found."

            # Get references attached to this paper
            refs = self._db.query(Reference).join(
                PaperReference, PaperReference.reference_id == Reference.id
            ).filter(
                PaperReference.paper_id == resolved_id
            ).limit(25).all()

            if not refs:
                return "No references attached to this paper."

            # Try semantic search with embeddings
            result = self._semantic_search(query, refs, max_results)
            if result:
                return result

            # Fallback to keyword search
            return self._keyword_search(query, refs, max_results)

        except Exception as e:
            logger.error(f"Reference search failed: {e}")
            return f"Error searching references: {str(e)}"

    def _semantic_search(self, query: str, refs: list, max_results: int) -> str:
        """Semantic search using embeddings."""
        try:
            from app.models.document_chunk import DocumentChunk
            from openai import OpenAI
            import os
            import json

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                return ""

            client = OpenAI(api_key=api_key)

            # Generate query embedding
            resp = client.embeddings.create(
                model="text-embedding-3-small",
                input=query[:8000]
            )
            query_embedding = resp.data[0].embedding

            def cosine_similarity(a, b):
                import math
                dot = sum(x * y for x, y in zip(a, b))
                norm_a = math.sqrt(sum(x * x for x in a))
                norm_b = math.sqrt(sum(x * x for x in b))
                return dot / (norm_a * norm_b) if norm_a and norm_b else 0

            results = []
            for ref in refs:
                chunks = self._db.query(DocumentChunk).filter(
                    DocumentChunk.reference_id == ref.id
                ).all()

                for chunk in chunks:
                    if not chunk.chunk_text or not chunk.embedding:
                        continue

                    emb = chunk.embedding
                    if isinstance(emb, str):
                        try:
                            emb = json.loads(emb)
                        except:
                            continue

                    if isinstance(emb, (list, tuple)) and len(emb) > 0:
                        score = cosine_similarity(query_embedding, emb)
                        results.append((ref, chunk, score))

            # Sort by relevance
            results.sort(key=lambda x: x[2], reverse=True)
            top_results = results[:max_results]

            if not top_results:
                return ""

            lines = [f"=== SEARCH RESULTS (semantic, {len(top_results)} matches) ===\n"]
            for ref, chunk, score in top_results:
                authors = ", ".join(ref.authors[:2]) + (" et al." if len(ref.authors) > 2 else "") if ref.authors else "Unknown"
                lines.append(f"From: {ref.title} ({authors}) [relevance: {score:.2f}]")
                lines.append(chunk.chunk_text[:500])
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return ""

    def _keyword_search(self, query: str, refs: list, max_results: int) -> str:
        """Fallback keyword-based search."""
        try:
            from app.models.document_chunk import DocumentChunk

            query_words = set(query.lower().split())
            results = []

            for ref in refs:
                chunks = self._db.query(DocumentChunk).filter(
                    DocumentChunk.reference_id == ref.id
                ).all()

                for chunk in chunks:
                    if not chunk.chunk_text:
                        continue
                    text_lower = chunk.chunk_text.lower()
                    score = sum(1 for w in query_words if w in text_lower)
                    if score > 0:
                        results.append((ref, chunk, score))

            results.sort(key=lambda x: x[2], reverse=True)
            top_results = results[:max_results]

            if not top_results:
                # Return metadata only
                lines = [f"No matching content found. {len(refs)} references available:"]
                for i, ref in enumerate(refs[:10], 1):
                    authors = ", ".join(ref.authors[:2]) + (" et al." if len(ref.authors) > 2 else "") if ref.authors else "Unknown"
                    lines.append(f"{i}. {ref.title} ({authors})")
                return "\n".join(lines)

            lines = [f"=== SEARCH RESULTS (keyword, {len(top_results)} matches) ===\n"]
            for ref, chunk, score in top_results:
                authors = ", ".join(ref.authors[:2]) + (" et al." if len(ref.authors) > 2 else "") if ref.authors else "Unknown"
                lines.append(f"From: {ref.title} ({authors})")
                lines.append(chunk.chunk_text[:500])
                lines.append("")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Keyword search failed: {e}")
            return ""

    def _handle_list_templates(self) -> Generator[str, None, None]:
        """Return formatted list of available templates."""
        yield "## Available Conference Templates\n\n"
        yield "| Template | ID | Notes |\n"
        yield "|----------|-----|-------|\n"
        yield "| IEEE Conference | `ieee` | Two-column, IEEEtran class |\n"
        yield "| ACL/EMNLP/NAACL | `acl` | NLP conferences |\n"
        yield "| NeurIPS | `neurips` | ML conference |\n"
        yield "| ICML | `icml` | ML conference |\n"
        yield "| ICLR | `iclr` | ML conference |\n"
        yield "| CVPR/ICCV | `cvpr` | Computer vision |\n"
        yield "| Nature/Science | `nature` | High-impact journals |\n"
        yield "| Elsevier | `elsevier` | Journal format |\n"
        yield "| Generic | `generic` | Simple article |\n"
        yield "\nTo convert, say: \"Convert to IEEE format\"\n"

    def _handle_apply_template(self, template_id: str) -> Generator[str, None, None]:
        """Return template info for AI to use with propose_edit."""
        if template_id not in CONFERENCE_TEMPLATES:
            yield f"Unknown template: `{template_id}`. Available: {', '.join(CONFERENCE_TEMPLATES.keys())}"
            return

        template = CONFERENCE_TEMPLATES[template_id]

        yield f"## Template: {template['name']}\n\n"
        yield f"{template['description']}\n\n"

        yield "### EXACT Preamble Structure to Use\n\n"
        yield "Copy this structure and fill in the actual title/authors from the document:\n\n"
        yield f"```latex\n{template['preamble_example']}\n```\n\n"

        yield f"### Author Format: `{template['author_format']}`\n\n"
        yield f"### Bibliography: `\\bibliographystyle{{{template['bib_style']}}}`\n\n"
        yield f"### Notes: {template['notes']}\n\n"

        yield "---\n\n"
        yield "**NOW call propose_edit** to replace lines 1 through \\maketitle with this template.\n"
        yield "Extract the title, authors, affiliations, and emails from the current document and plug them into the template structure above.\n"
