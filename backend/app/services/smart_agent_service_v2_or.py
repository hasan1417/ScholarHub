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
import concurrent.futures
from typing import Optional, Generator, List, Dict, Any
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session
from openai import OpenAI

from app.services.smart_agent_service_v2 import (
    EDITOR_TOOLS,
    SYSTEM_PROMPT,
    _resolve_paper_id,
)
from app.services.discussion_ai.openrouter_orchestrator import model_supports_reasoning
from app.services.discussion_ai.token_utils import (
    count_tokens,
    count_messages_tokens,
    fit_messages_in_budget,
    get_context_limit,
    RESPONSE_TOKEN_RESERVE,
    TOOL_OUTPUT_RESERVE,
)
from app.constants.paper_templates import CONFERENCE_TEMPLATES

logger = logging.getLogger(__name__)

# Background thread pool for async summary updates (shared, bounded)
_summary_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2, thread_name_prefix="editor-summary")

# Summary trigger thresholds
_SUMMARY_MSG_THRESHOLD = 16  # Total messages before considering summary
_SUMMARY_STALE_THRESHOLD = 6  # New messages since last summary before re-summarizing


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

    _LITE_SYSTEM_PROMPT = (
        "You are a helpful academic writing assistant for the LaTeX editor in ScholarHub. "
        "Respond concisely and warmly. If the user greets you, greet them back briefly. "
        "If they thank you or acknowledge something, confirm briefly. "
        "If they seem to need editing help, let them know you're ready. "
        "Keep responses under 2 sentences."
    )

    _EDITOR_ACTION_VERBS = re.compile(
        r"\b(improve|fix|rewrite|shorten|expand|change|edit|modify|correct|proofread|"
        r"convert|reformat|replace|insert|delete|remove|rephrase|revise|polish|"
        r"make better|tighten|clean up|strengthen)\b",
        re.IGNORECASE,
    )

    def _is_lite_route(self, query: str, history: List[Dict[str, str]]) -> bool:
        """Check if this message should take the lite path (no tools, no document)."""
        if self._EDITOR_ACTION_VERBS.search(query or ""):
            return False
        from app.services.discussion_ai.route_classifier import classify_route
        decision = classify_route(query, history, {})
        return decision.route == "lite"

    def _execute_lite(self, query: str, history: List[Dict[str, str]]) -> str:
        """Single lightweight LLM call — no tools, no document context."""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._LITE_SYSTEM_PROMPT},
        ]
        for msg in history[-4:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": query})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=150,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"[SmartAgentV2OR] Lite execution error: {e}")
            return "Hello! I can help you edit, review, or answer questions about your paper. What would you like to do?"

    def _emit_status(self, message: str) -> str:
        """Return a status marker for the frontend. Never touches response_text."""
        logger.debug("[SmartAgentV2OR][paper=%s] status=%s", self._paper_id, message)
        return f"[[[STATUS:{message}]]]"

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
        project_id: Optional[str] = None,
        document_excerpt: Optional[str] = None,
        reasoning_mode: bool = False,
        user_name: str = "User",
    ) -> Generator[str, None, None]:
        """Stream response using OpenRouter."""

        if not self.client:
            yield "OpenRouter API key not configured."
            return

        # Store for reference search tool
        self._db = db
        self._user_id = user_id
        self._user_name = user_name
        self._paper_id = paper_id
        self._last_tools_called: List[str] = []

        yield self._emit_status("Classifying request")

        # Lite route: greetings, acks, short messages — lightweight LLM, no tools/document
        history_for_route = self._get_recent_history(db, paper_id, project_id, limit=4)
        if self._is_lite_route(query, history_for_route):
            yield self._emit_status("Generating response")
            lite_response = self._execute_lite(query, history_for_route)
            yield lite_response
            self._store_chat_exchange(
                db=db, user_id=user_id, paper_id=paper_id,
                project_id=project_id, user_message=query,
                assistant_message=lite_response,
            )
            return

        yield self._emit_status("Loading references")
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

        yield self._emit_status("Building context")
        history_messages, summary_block = self._build_context_with_budget(
            db=db,
            paper_id=paper_id,
            project_id=project_id,
            document_tokens=count_tokens(full_context),
        )

        # Build tools list (add reference search)
        tools = list(EDITOR_TOOLS) + [SEARCH_REFERENCES_TOOL]
        effective_query = self._rewrite_affirmation(query, history_messages) or query
        if effective_query.strip().lower().startswith("clarification:"):
            tools = [tool for tool in tools if tool["function"]["name"] != "ask_clarification"]

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        if summary_block:
            messages.append({"role": "system", "content": summary_block})
        messages.extend(history_messages)
        messages.append({"role": "user", "content": f"{full_context}\n\n---\n\nUser request: {effective_query}"})

        try:
            # Multi-turn for reference searches only
            max_turns = 3
            turn = 0
            response_text = ""

            def _collect_and_yield(gen: Generator[str, None, None]) -> Generator[str, None, None]:
                nonlocal response_text
                for chunk in gen:
                    response_text += chunk
                    yield chunk

            yield self._emit_status("Analyzing request")
            clarification = self._build_clarification(effective_query, document_excerpt)
            if clarification:
                yield from _collect_and_yield(self._format_tool_response("ask_clarification", clarification))
                self._store_chat_exchange(
                    db=db,
                    user_id=user_id,
                    paper_id=paper_id,
                    project_id=project_id,
                    user_message=effective_query,
                    assistant_message=response_text,
                )
                return

            while turn < max_turns:
                turn += 1

                yield self._emit_status("Generating response" if turn == 1 else "Processing results")

                tool_choice = "required" if turn == 1 else "auto"
                if turn == 1 and not self._should_require_tool_choice(effective_query):
                    tool_choice = "auto"

                request_kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": tool_choice,
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
                    self._last_tools_called.append(tool_name)

                    logger.info(f"[SmartAgentV2OR] Turn {turn}: {tool_name}")

                    # Intermediate tools - return info to AI for further processing
                    if tool_name == "search_references":
                        yield self._emit_status("Searching references")
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
                        yield self._emit_status("Applying template")
                        template_info = "".join(self._handle_apply_template(tool_args.get("template_id", "")))
                        messages.append(choice.message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": template_info
                        })
                        continue  # AI will call propose_edit next

                    elif tool_name == "review_document":
                        yield self._emit_status("Reviewing document")
                        review_output = "".join(self._format_tool_response(tool_name, tool_args))
                        messages.append(choice.message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": review_output
                        })
                        continue  # Let AI decide if it wants to propose edits

                    elif tool_name == "list_available_templates":
                        yield self._emit_status("Loading templates")
                        list_output = "".join(self._format_tool_response(tool_name, tool_args))
                        messages.append(choice.message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": list_output
                        })
                        continue  # Let AI decide next action

                    # All other tools - format and return
                    yield from _collect_and_yield(self._format_tool_response(tool_name, tool_args))
                    self._store_chat_exchange(
                        db=db,
                        user_id=user_id,
                        paper_id=paper_id,
                        project_id=project_id,
                        user_message=effective_query,
                        assistant_message=response_text,
                    )
                    return

                elif choice.message.content:
                    response_text = choice.message.content
                    yield choice.message.content
                    self._store_chat_exchange(
                        db=db,
                        user_id=user_id,
                        paper_id=paper_id,
                        project_id=project_id,
                        user_message=effective_query,
                        assistant_message=response_text,
                    )
                    return

            response_text = "Could not complete the request. Please try again."
            yield response_text
            self._store_chat_exchange(
                db=db,
                user_id=user_id,
                paper_id=paper_id,
                project_id=project_id,
                user_message=effective_query,
                assistant_message=response_text,
            )

        except Exception as e:
            logger.error(f"[SmartAgentV2OR] Error: {e}")
            yield f"Sorry, an error occurred: {str(e)}"

    def _build_clarification(self, query: str, document_excerpt: Optional[str]) -> Optional[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return None
        q_lower = q.lower()
        if q_lower.startswith("clarification:"):
            return None
        if q_lower.endswith("?") and q_lower.split(" ", 1)[0] in ("what", "which", "how", "when", "where", "who", "why"):
            return None
        if self._is_convert_request(q_lower):
            return None

        operation = self._detect_operation(q_lower)
        if not operation:
            return None

        target = self._detect_target(q_lower)
        if not target and document_excerpt:
            target = "document"

        if self._has_explicit_replacement(q_lower, q):
            return None

        if not target:
            return {
                "question": "What should I change?",
                "options": [
                    "Title",
                    "Abstract",
                    "Specific section (tell me which)",
                    "Entire document",
                ],
            }

        if operation == "fix":
            return None

        if operation in ("improve", "rewrite", "shorten", "expand", "change") and not self._has_constraints(q_lower):
            return {
                "question": f"For the {target}, what should I optimize for?",
                "options": [
                    "Shorter/concise",
                    "More specific focus",
                    "More formal/academic",
                    "Improve clarity/flow",
                ],
            }

        return None

    def _detect_operation(self, q_lower: str) -> Optional[str]:
        if any(term in q_lower for term in ("fix grammar", "fix typos", "grammar", "typo", "proofread")):
            return "fix"
        if any(term in q_lower for term in ("shorten", "condense", "compress", "summarize", "trim", "cut", "reduce", "make shorter", "make concise")):
            return "shorten"
        if any(term in q_lower for term in ("expand", "elaborate", "add detail", "lengthen", "add more")):
            return "expand"
        if any(term in q_lower for term in ("rewrite", "rephrase", "paraphrase", "reword")):
            return "rewrite"
        if any(term in q_lower for term in ("improve", "make better", "enhance", "polish", "refine", "tighten", "clean up", "strengthen", "revise")):
            return "improve"
        if any(term in q_lower for term in ("change", "update")):
            return "change"
        return None

    def _detect_target(self, q_lower: str) -> Optional[str]:
        targets = (
            "title",
            "abstract",
            "introduction",
            "background",
            "related work",
            "literature review",
            "method",
            "methods",
            "methodology",
            "results",
            "discussion",
            "conclusion",
            "limitations",
            "section",
            "paragraph",
            "sentence",
            "document",
            "paper",
            "manuscript",
        )
        for term in targets:
            if term in q_lower:
                return term
        return None

    def _has_constraints(self, q_lower: str) -> bool:
        if re.search(r"\b\d+\s*(words?|pages?|sentences?)\b", q_lower):
            return True
        if any(term in q_lower for term in ("shorter", "longer", "concise", "brief", "detailed", "in depth")):
            return True
        if any(term in q_lower for term in ("focus", "emphasize", "highlight", "specifically", "scope", "about")):
            return True
        if any(term in q_lower for term in ("tone", "formal", "academic", "casual", "technical", "simple", "professional")):
            return True
        if any(term in q_lower for term in ("suggest", "options", "examples", "alternatives")):
            return True
        return False

    def _is_convert_request(self, q_lower: str) -> bool:
        if any(term in q_lower for term in ("convert", "reformat", "template")):
            return True
        for template_id in CONFERENCE_TEMPLATES.keys():
            if template_id in q_lower:
                return True
        return False

    def _has_explicit_replacement(self, q_lower: str, query: str) -> bool:
        if '"' in query or "'" in query or "\\title{" in query:
            return True
        if re.search(r"\btitle\b.*\bto\b.{5,}", q_lower):
            return True
        return False

    def _is_review_message(self, content: str) -> bool:
        if not content:
            return False
        return "## Review" in content or "Suggested Improvements" in content

    def _rewrite_affirmation(self, query: str, history: List[Dict[str, str]]) -> Optional[str]:
        q = (query or "").strip().lower()
        if not q:
            return None
        short_ack = {
            "please",
            "yes",
            "ok",
            "okay",
            "sure",
            "go ahead",
            "do it",
            "do so",
            "apply",
            "apply it",
            "sounds good",
            "yep",
        }
        if q not in short_ack:
            return None
        last_assistant = next((m for m in reversed(history) if m.get("role") == "assistant"), None)
        if not last_assistant or not self._is_review_message(last_assistant.get("content", "")):
            return None
        return "Apply the suggested changes from your last review."

    def _sanitize_assistant_content(self, content: str) -> str:
        if "<<<EDIT>>>" in content:
            content = content.split("<<<EDIT>>>", 1)[0].strip()
        if "<<<CLARIFY>>>" in content:
            content = content.split("<<<CLARIFY>>>", 1)[0].strip()
        return content

    def _should_require_tool_choice(self, query: str) -> bool:
        q = (query or "").strip().lower()
        if not q:
            return True
        if "apply all suggested changes" in q or "apply suggested changes" in q or "apply all suggestions" in q:
            return False
        if "apply critical fixes" in q or "apply critical" in q:
            return False
        return True

    def _get_recent_history(
        self,
        db: Session,
        paper_id: Optional[str],
        project_id: Optional[str],
        limit: int = 20,
    ) -> List[Dict[str, str]]:
        """Load recent chat history shared across all collaborators, with speaker names."""
        try:
            if not paper_id and not project_id:
                return []
            from app.models.editor_chat_message import EditorChatMessage
            from app.models.user import User

            q = db.query(EditorChatMessage, User.first_name).outerjoin(
                User, EditorChatMessage.user_id == User.id
            )
            if paper_id:
                q = q.filter(EditorChatMessage.paper_id == str(paper_id))
            elif project_id:
                q = q.filter(EditorChatMessage.project_id == str(project_id))

            rows = (
                q.order_by(EditorChatMessage.created_at.desc(), EditorChatMessage.id.desc())
                .limit(limit)
                .all()
            )
            if not isinstance(rows, list):
                return []

            history = []
            for row, first_name in reversed(rows):
                if row.role not in ("user", "assistant"):
                    continue
                content = row.content or ""
                if row.role == "assistant":
                    content = self._sanitize_assistant_content(content)
                    if not content:
                        continue
                    history.append({"role": "assistant", "content": content})
                else:
                    speaker = first_name or "User"
                    history.append({"role": "user", "content": f"{speaker}: {content}"})
            return history
        except Exception as e:
            logger.warning(f"[SmartAgentV2OR] Failed to load editor history: {e}")
            return []

    def _build_context_with_budget(
        self,
        db: Session,
        paper_id: Optional[str],
        project_id: Optional[str],
        document_tokens: int = 0,
    ) -> tuple:
        """Build token-managed context: (history_messages, summary_block_or_None)."""
        # Load rolling summary from paper if available
        summary_block = None
        if paper_id:
            try:
                from app.models.research_paper import ResearchPaper
                paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
                if paper and paper.editor_ai_context:
                    existing_summary = paper.editor_ai_context.get("summary", "")
                    if existing_summary:
                        summary_block = f"[Previous conversation summary]\n{existing_summary}\n[Recent conversation]"
            except Exception as e:
                logger.warning(f"[SmartAgentV2OR] Failed to load ai context: {e}")

        # Calculate budget
        total_limit = get_context_limit(self.model)
        system_tokens = count_tokens(SYSTEM_PROMPT) + 50  # overhead
        summary_tokens = count_tokens(summary_block) if summary_block else 0
        available = total_limit - RESPONSE_TOKEN_RESERVE - TOOL_OUTPUT_RESERVE - system_tokens - document_tokens - summary_tokens
        history_budget = min(available, 8000)  # Cap at 8000 tokens for history

        # Load recent history
        history = self._get_recent_history(db, paper_id, project_id, limit=20)

        if not history:
            return [], summary_block

        # Fit messages within budget
        fitted, _ = fit_messages_in_budget(history, history_budget, model=self.model, keep_newest=True)
        return fitted, summary_block

    def _store_chat_exchange(
        self,
        db: Session,
        user_id: str,
        paper_id: Optional[str],
        project_id: Optional[str],
        user_message: str,
        assistant_message: str,
    ) -> None:
        if not assistant_message or (not paper_id and not project_id):
            return
        try:
            from app.models.editor_chat_message import EditorChatMessage

            db.add(EditorChatMessage(
                user_id=user_id,
                paper_id=str(paper_id) if paper_id else None,
                project_id=str(project_id) if project_id else None,
                role="user",
                content=user_message,
            ))
            db.add(EditorChatMessage(
                user_id=user_id,
                paper_id=str(paper_id) if paper_id else None,
                project_id=str(project_id) if project_id else None,
                role="assistant",
                content=assistant_message,
            ))
            db.commit()

            # Persist _last_tools_called in editor_ai_context
            tools_called = getattr(self, "_last_tools_called", [])
            if paper_id:
                try:
                    tools_json = json.dumps({"_last_tools_called": tools_called})
                    db.execute(
                        sa_text("""
                            UPDATE research_papers
                            SET editor_ai_context = editor_ai_context || CAST(:tools_data AS jsonb)
                            WHERE id = CAST(:paper_id AS uuid)
                        """),
                        {"tools_data": tools_json, "paper_id": str(paper_id)},
                    )
                    db.commit()
                except Exception as e:
                    db.rollback()
                    logger.warning(f"[SmartAgentV2OR] Failed to persist tools_called: {e}")

            # Check if we should trigger background summary
            if paper_id:
                self._maybe_trigger_summary(paper_id)

        except Exception as e:
            db.rollback()
            logger.warning(f"[SmartAgentV2OR] Failed to store editor chat: {e}")

    def _maybe_trigger_summary(self, paper_id: str) -> None:
        """Check message count and trigger background summary if needed."""
        try:
            from app.models.editor_chat_message import EditorChatMessage
            total = self._db.query(EditorChatMessage).filter(
                EditorChatMessage.paper_id == str(paper_id)
            ).count()

            if total < _SUMMARY_MSG_THRESHOLD:
                return

            # Check if summary is stale
            from app.models.research_paper import ResearchPaper
            paper = self._db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
            if not paper:
                return
            ctx = paper.editor_ai_context or {}
            last_summarized_id = ctx.get("last_summarized_id")

            if last_summarized_id:
                new_since = self._db.query(EditorChatMessage).filter(
                    EditorChatMessage.paper_id == str(paper_id),
                    EditorChatMessage.created_at > self._db.query(EditorChatMessage.created_at).filter(
                        EditorChatMessage.id == last_summarized_id
                    ).scalar_subquery(),
                ).count()
                if new_since < _SUMMARY_STALE_THRESHOLD:
                    return

            # Fire background summary
            context_version = ctx.get("context_version", 0)
            existing_summary = ctx.get("summary", "")
            api_key = self.client.api_key if self.client else None
            model = self.model

            future = _summary_executor.submit(
                _run_background_summary,
                paper_id=str(paper_id),
                context_version=context_version,
                existing_summary=existing_summary,
                api_key=api_key,
                model=model,
            )
            future.add_done_callback(_summary_done_callback)

        except Exception as e:
            logger.warning(f"[SmartAgentV2OR] Failed to check summary trigger: {e}")

    def _format_tool_response(self, tool_name: str, args: dict) -> Generator[str, None, None]:
        """Format the tool response for the frontend."""

        if tool_name == "answer_question":
            yield args.get("answer", "")

        elif tool_name == "ask_clarification":
            question = (args.get("question") or "").strip()
            raw_options = args.get("options") or []
            if isinstance(raw_options, str):
                raw_options = [raw_options]
            options = [opt.strip() for opt in raw_options if isinstance(opt, str) and opt.strip()]

            yield "<<<CLARIFY>>>\n"
            yield f"QUESTION: {question}\n"
            yield f"OPTIONS: {' | '.join(options)}\n"
            yield "<<<END>>>\n"

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

        elif tool_name == "apply_template":
            yield from self._handle_apply_template(args.get("template_id", ""))

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
                status_bits = []
                document = getattr(ref, "document", None)
                if document is not None:
                    doc_status = getattr(document.status, "value", None) or str(document.status)
                    if getattr(document, "is_processed_for_ai", False):
                        status_bits.append("full text ready")
                    elif doc_status in {"processing", "uploading"}:
                        status_bits.append("processing")
                    elif doc_status:
                        status_bits.append(doc_status)
                if ref.pdf_url and not status_bits:
                    status_bits.append("pdf linked")

                status_suffix = f" — {', '.join(status_bits)}" if status_bits else ""
                lines.append(f"{i}. {ref.title} ({authors}, {ref.year or 'n.d.'}){status_suffix}")
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
        for template_id, template in CONFERENCE_TEMPLATES.items():
            name = template.get("name", template_id)
            notes = template.get("notes", "")
            yield f"| {name} | `{template_id}` | {notes} |\n"
        yield "\nTo convert, say: \"Convert this to ACL format\" or \"Reformat for IEEE\"\n"

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
        yield "### Recommended Sections\n\n"
        for section in template.get("sections", []):
            yield f"- {section}\n"
        yield "\n"
        yield f"### Notes: {template['notes']}\n\n"

        yield "---\n\n"
        yield "**NOW call propose_edit** to replace lines 1 through \\maketitle with this template.\n"
        yield "Extract the title, authors, affiliations, and emails from the current document and plug them into the template structure above.\n"


def _summary_done_callback(future: concurrent.futures.Future) -> None:
    """Log exceptions from background summary tasks."""
    try:
        future.result()
    except Exception as e:
        logger.error(f"[SmartAgentV2OR] Background summary failed: {e}")


def _run_background_summary(
    paper_id: str,
    context_version: int,
    existing_summary: str,
    api_key: Optional[str],
    model: str,
) -> None:
    """Run rolling summary in a background thread with its own DB session."""
    from app.database import SessionLocal
    from app.models.editor_chat_message import EditorChatMessage
    from app.models.user import User

    if not api_key:
        return

    db = SessionLocal()
    try:
        # Load messages for summarization (oldest first, up to 30)
        rows = (
            db.query(EditorChatMessage, User.first_name)
            .outerjoin(User, EditorChatMessage.user_id == User.id)
            .filter(EditorChatMessage.paper_id == paper_id)
            .order_by(EditorChatMessage.created_at.asc())
            .limit(30)
            .all()
        )
        if not rows:
            return

        # Format for summarization prompt
        message_lines = []
        last_msg_id = None
        for msg, first_name in rows:
            speaker = first_name or "User" if msg.role == "user" else "AI"
            message_lines.append(f"{speaker}: {(msg.content or '')[:500]}")
            last_msg_id = str(msg.id)

        message_text = "\n".join(message_lines)

        if existing_summary:
            prompt = f"""You are summarizing an academic paper editing conversation for context retention.

EXISTING SUMMARY:
{existing_summary}

NEW MESSAGES:
{message_text}

Create an UPDATED summary that:
1. Preserves key information from the existing summary
2. Incorporates new developments
3. Focuses on: editing decisions, format changes, sections worked on, open tasks
4. Notes who asked for what (speaker names)
5. Keeps it under 250 words
6. Uses bullet points

Updated Summary:"""
        else:
            prompt = f"""Summarize this academic paper editing conversation for context retention.

MESSAGES:
{message_text}

Create a summary that:
1. Captures the main editing tasks and decisions
2. Notes who asked for what (speaker names)
3. Lists any format/template changes
4. Highlights sections that were edited
5. Keeps it under 250 words
6. Uses bullet points

Summary:"""

        # Make LLM call
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub Editor Summary"
            }
        )
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=400,
            temperature=0.3,
        )
        new_summary = response.choices[0].message.content.strip()
        if not new_summary:
            return

        # Atomic optimistic locking: single UPDATE ... WHERE context_version = expected
        new_version = context_version + 1
        new_ctx = json.dumps({
            "summary": new_summary,
            "last_summarized_id": last_msg_id,
            "context_version": new_version,
        })

        result = db.execute(
            sa_text("""
                UPDATE research_papers
                SET editor_ai_context = editor_ai_context || CAST(:new_data AS jsonb)
                WHERE id = CAST(:paper_id AS uuid)
                  AND COALESCE(CAST(editor_ai_context->>'context_version' AS int), 0) = :expected_version
            """),
            {"new_data": new_ctx, "paper_id": paper_id, "expected_version": context_version},
        )
        db.commit()

        if result.rowcount == 0:
            logger.info(f"[SmartAgentV2OR] Summary skipped - version conflict (expected {context_version})")
        else:
            logger.info(f"[SmartAgentV2OR] Background summary saved for paper {paper_id} (v{new_version})")

    except Exception as e:
        logger.error(f"[SmartAgentV2OR] Background summary error: {e}")
        db.rollback()
    finally:
        db.close()
