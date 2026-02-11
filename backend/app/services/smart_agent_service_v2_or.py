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
import time
import logging
import concurrent.futures
from typing import Optional, Generator, List, Dict, Any, Tuple
from sqlalchemy import text as sa_text
from sqlalchemy.orm import Session
from openai import OpenAI

from app.core.config import settings
from app.services.smart_agent_service_v2 import (
    EDITOR_TOOLS,
    SYSTEM_PROMPT,
    _resolve_paper_id,
)
from app.services.discussion_ai.openrouter_orchestrator import model_supports_reasoning, ThinkTagFilter
from app.services.discussion_ai.token_utils import (
    count_tokens,
    fit_messages_in_budget,
    get_context_limit,
    RESPONSE_TOKEN_RESERVE,
    TOOL_OUTPUT_RESERVE,
)
from app.constants.paper_templates import CONFERENCE_TEMPLATES

logger = logging.getLogger(__name__)

# Feature flag: stream answer_question tool arguments in real-time.
# Set to True once logs confirm stability of Steps 1-3.
STREAM_ANSWER_ARGS = os.getenv("EDITOR_STREAM_ANSWER_ARGS", "").lower() in ("1", "true", "yes")

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
        "description": "Search the full text of attached references using semantic search. Use this to retrieve detailed content, methods, findings, or any specific information from papers marked 'full text ready'. The initial reference list only shows abstracts — call this tool to access the complete paper text.",
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
        r"make better|tighten|clean up|strengthen|enhance)\b",
        re.IGNORECASE,
    )

    def _is_lite_route(self, query: str, history: List[Dict[str, str]]) -> bool:
        """Check if this message should take the lite path (no tools, no document)."""
        if self._EDITOR_ACTION_VERBS.search(query or ""):
            return False
        from app.services.discussion_ai.route_classifier import classify_route
        decision = classify_route(query, history, {})
        return decision.route == "lite"

    def _emit_status(self, message: str) -> str:
        """Return a status marker for the frontend. Never touches response_text."""
        logger.debug("[SmartAgentV2OR][paper=%s] status=%s", self._paper_id, message)
        return f"[[[STATUS:{message}]]]"

    @staticmethod
    def _unescape_json_partial(buffer: str) -> Tuple[str, str]:
        """Unescape JSON string content from a partial buffer.

        Returns (unescaped_text, remaining_buffer).
        Stops at unescaped closing quote or end of buffer.
        """
        out: list[str] = []
        i = 0
        while i < len(buffer):
            ch = buffer[i]
            if ch == '"':
                return "".join(out), buffer[i + 1:]
            if ch == '\\':
                if i + 1 >= len(buffer):
                    return "".join(out), buffer[i:]
                nxt = buffer[i + 1]
                if nxt == 'n':
                    out.append('\n')
                elif nxt == 't':
                    out.append('\t')
                elif nxt == 'r':
                    out.append('\r')
                elif nxt in ('"', '\\', '/'):
                    out.append(nxt)
                elif nxt == 'u':
                    if i + 5 < len(buffer):
                        try:
                            out.append(chr(int(buffer[i + 2:i + 6], 16)))
                        except ValueError:
                            out.append(buffer[i + 2:i + 6])
                        i += 6
                        continue
                    else:
                        return "".join(out), buffer[i:]
                else:
                    out.append(nxt)
                i += 2
            else:
                out.append(ch)
                i += 1
        return "".join(out), ""

    def _stream_llm_call(self, request_kwargs: dict) -> Generator[str, None, None]:
        """Stream an LLM call, yielding visible content tokens.

        After exhaustion, check:
        - self._last_stream_content: accumulated content text
        - self._last_stream_tool_calls: list of {id, name, arguments_raw} dicts
        - self._answer_was_streamed: True if answer_question args were live-streamed
        """
        request_kwargs = {**request_kwargs, "stream": True}

        think_filter = ThinkTagFilter()
        content_parts: list[str] = []
        tool_calls_data: dict[int, dict] = {}
        tool_call_detected = False

        # Tool-specific status emission (once, when tool name is known)
        _tool_status_emitted = False
        _TOOL_STATUS_LABELS = {
            "propose_edit": "Preparing edits",
            "apply_template": "Loading template",
            "search_references": "Searching references",
            "review_document": "Reviewing document",
            "answer_question": "Generating answer",
        }

        # answer_question arg-live streaming state
        answer_streaming = False
        answer_aborted = False
        answer_arg_buffer = ""
        answer_empty_count = 0
        _ANSWER_PREFIXES = ('"answer": "', '"answer":"')

        first_content_time: Optional[float] = None

        try:
            stream = self.client.chat.completions.create(**request_kwargs)

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Content tokens — yield until tool call detected
                if delta.content and not tool_call_detected:
                    content_parts.append(delta.content)
                    visible = think_filter.feed(delta.content)
                    if visible:
                        if first_content_time is None:
                            first_content_time = time.monotonic()
                        yield visible

                # Tool call deltas
                if delta.tool_calls:
                    if not tool_call_detected:
                        tool_call_detected = True
                        remaining = think_filter.flush()
                        if remaining:
                            if first_content_time is None:
                                first_content_time = time.monotonic()
                            yield remaining

                    for tc_chunk in delta.tool_calls:
                        idx = tc_chunk.index
                        if idx not in tool_calls_data:
                            tool_calls_data[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_chunk.id:
                            tool_calls_data[idx]["id"] = tc_chunk.id
                        if tc_chunk.function:
                            if tc_chunk.function.name:
                                tool_calls_data[idx]["name"] = tc_chunk.function.name
                                # Emit tool-specific status once name is known
                                if not _tool_status_emitted:
                                    _tool_status_emitted = True
                                    label = _TOOL_STATUS_LABELS.get(tc_chunk.function.name, "Processing")
                                    yield self._emit_status(label)
                            if tc_chunk.function.arguments:
                                arg_frag = tc_chunk.function.arguments
                                tool_calls_data[idx]["arguments"] += arg_frag

                                # Step 4: answer_question arg-live streaming (feature-flagged)
                                if (
                                    STREAM_ANSWER_ARGS
                                    and idx == 0
                                    and tool_calls_data[idx]["name"] == "answer_question"
                                    and not answer_aborted
                                ):
                                    if not answer_streaming:
                                        answer_arg_buffer += arg_frag
                                        for prefix in _ANSWER_PREFIXES:
                                            pos = answer_arg_buffer.find(prefix)
                                            if pos != -1:
                                                answer_streaming = True
                                                answer_arg_buffer = answer_arg_buffer[pos + len(prefix):]
                                                break
                                        if answer_streaming and answer_arg_buffer:
                                            text, answer_arg_buffer = self._unescape_json_partial(answer_arg_buffer)
                                            if text:
                                                visible = think_filter.feed(text)
                                                if visible:
                                                    if first_content_time is None:
                                                        first_content_time = time.monotonic()
                                                    yield visible
                                                answer_empty_count = 0
                                            else:
                                                answer_empty_count += 1
                                    else:
                                        answer_arg_buffer += arg_frag
                                        text, answer_arg_buffer = self._unescape_json_partial(answer_arg_buffer)
                                        if text:
                                            visible = think_filter.feed(text)
                                            if visible:
                                                if first_content_time is None:
                                                    first_content_time = time.monotonic()
                                                yield visible
                                            answer_empty_count = 0
                                        else:
                                            answer_empty_count += 1

                                    # Strict fallback: abort if 3+ consecutive empty deltas
                                    if answer_empty_count >= 3 and answer_streaming:
                                        answer_aborted = True
                                        answer_streaming = False
                                        logger.warning("[SmartAgentV2OR] answer arg-live aborted (parse confidence drop)")

            # Flush ThinkTagFilter
            remaining = think_filter.flush()
            if remaining:
                if first_content_time is None:
                    first_content_time = time.monotonic()
                yield remaining

        except Exception as e:
            logger.error(f"[SmartAgentV2OR] Stream error: {e}")
            raise

        # Store results for caller
        self._last_stream_content = "".join(content_parts)
        self._last_stream_tool_calls = [
            {"id": tc["id"], "name": tc["name"], "arguments_raw": tc["arguments"]}
            for idx in sorted(tool_calls_data.keys())
            for tc in [tool_calls_data[idx]]
        ]
        self._answer_was_streamed = answer_streaming and not answer_aborted
        self._first_content_time = first_content_time

    def _execute_lite_streaming(self, query: str, history: List[Dict[str, str]]) -> Generator[str, None, None]:
        """Streaming lite LLM call — no tools, no document context."""
        messages: List[Dict[str, str]] = [
            {"role": "system", "content": self._LITE_SYSTEM_PROMPT},
        ]
        for msg in history[-4:]:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": query})

        think_filter = ThinkTagFilter()

        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=150,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if delta.content:
                    visible = think_filter.feed(delta.content)
                    if visible:
                        yield visible

            remaining = think_filter.flush()
            if remaining:
                yield remaining

        except Exception as e:
            logger.warning(f"[SmartAgentV2OR] Lite streaming error: {e}")
            yield "Hello! I can help you edit, review, or answer questions about your paper. What would you like to do?"

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

        t_start = time.monotonic()
        self._first_content_time = None

        yield self._emit_status("Classifying request")

        # Lite route: greetings, acks, short messages — streaming lightweight LLM, no tools/document
        history_for_route = self._get_recent_history(db, paper_id, project_id, limit=4)
        if self._is_lite_route(query, history_for_route):
            yield self._emit_status("Generating response")
            lite_text = ""
            for token in self._execute_lite_streaming(query, history_for_route):
                if not lite_text and token.strip():
                    self._first_content_time = time.monotonic()
                lite_text += token
                yield token
            self._store_chat_exchange(
                db=db, user_id=user_id, paper_id=paper_id,
                project_id=project_id, user_message=query,
                assistant_message=lite_text,
            )
            ttfb = int((self._first_content_time - t_start) * 1000) if self._first_content_time else -1
            total = int((time.monotonic() - t_start) * 1000)
            logger.info("[SmartAgentV2OR][paper=%s] ttfb_ms=%d total_ms=%d turns=0 tool_calls=none (lite)", paper_id, ttfb, total)
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

            _STATUS_RE = re.compile(r"\[\[\[STATUS:.*?\]\]\]")

            def _collect_and_yield(gen: Generator[str, None, None]) -> Generator[str, None, None]:
                nonlocal response_text
                for chunk in gen:
                    # Strip status markers from stored text (they're UI-only)
                    clean = _STATUS_RE.sub("", chunk)
                    if clean:
                        response_text += clean
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
                total = int((time.monotonic() - t_start) * 1000)
                logger.info("[SmartAgentV2OR][paper=%s] ttfb_ms=-1 total_ms=%d turns=0 tool_calls=ask_clarification (early)", paper_id, total)
                return

            while turn < max_turns:
                turn += 1

                yield self._emit_status("Generating response" if turn == 1 else "Processing results")

                # Budget check: truncate tool results if messages exceed context limit
                if turn > 1:
                    ctx_limit = get_context_limit(self.model)
                    msg_tokens = sum(count_tokens(m.get("content") or "") for m in messages)
                    headroom = ctx_limit - 4000 - 500  # response tokens + overhead
                    if msg_tokens > headroom:
                        # Trim the most recent tool result to fit
                        for i in range(len(messages) - 1, -1, -1):
                            if messages[i].get("role") == "tool":
                                content = messages[i].get("content", "")
                                excess = msg_tokens - headroom
                                trim_chars = excess * 4  # ~4 chars per token
                                if trim_chars < len(content):
                                    messages[i]["content"] = content[:len(content) - trim_chars] + "\n\n[Truncated to fit context limit]"
                                else:
                                    messages[i]["content"] = content[:200] + "\n\n[Truncated to fit context limit]"
                                logger.warning("[SmartAgentV2OR] Trimmed tool result by ~%d tokens to fit context", excess)
                                break

                tool_choice = self._resolve_tool_choice(effective_query, turn)

                request_kwargs = {
                    "model": self.model,
                    "messages": messages,
                    "tools": tools,
                    "tool_choice": tool_choice,
                    "max_tokens": 4000,
                }

                if use_reasoning:
                    request_kwargs["extra_body"] = {"reasoning_effort": "high"}

                # Stream the LLM call — content tokens (and optionally
                # answer_question args) are yielded live via _collect_and_yield.
                yield from _collect_and_yield(self._stream_llm_call(request_kwargs))

                tool_calls = self._last_stream_tool_calls

                if not tool_calls:
                    # Content-only response — already streamed and accumulated
                    if not self._last_stream_content.strip() and turn > 1:
                        fallback = "\n\nI wasn't able to complete the full response. Please try again."
                        response_text += fallback
                        yield fallback
                    break

                tc = tool_calls[0]
                tool_name = tc["name"]
                raw_args = tc["arguments_raw"] or "{}"
                try:
                    tool_args = json.loads(raw_args)
                except json.JSONDecodeError:
                    logger.warning(f"[SmartAgentV2OR] Malformed tool args for {tool_name}: {raw_args[:100]}")
                    tool_args = {}
                    raw_args = "{}"  # Ensure valid JSON for multi-turn context
                self._last_tools_called.append(tool_name)
                logger.info(f"[SmartAgentV2OR] Turn {turn}: {tool_name}")

                # Build assistant message for multi-turn context
                assistant_msg: Dict[str, Any] = {
                    "role": "assistant",
                    "content": self._last_stream_content or "",
                    "tool_calls": [{
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tool_name, "arguments": raw_args},
                    }],
                }

                # Intermediate tools — execute and loop back
                if tool_name == "search_references":
                    yield self._emit_status("Searching references")
                    search_results = self._search_references_for_tool(
                        tool_args.get("query", ""), tool_args.get("max_results", 10),
                    )
                    messages.append(assistant_msg)
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": search_results})
                    continue

                elif tool_name == "apply_template":
                    # Guard: reject if user didn't ask for conversion
                    if not self._is_convert_request(effective_query.lower()):
                        messages.append(assistant_msg)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": "ERROR: apply_template is only for format conversion requests. "
                                       "The user asked about writing improvement. Use review_document or answer_question instead."
                        })
                        continue
                    yield self._emit_status("Applying template")
                    tid = tool_args.get("template_id", "")
                    if settings.EDITOR_DETERMINISTIC_CONVERT_V1:
                        from app.services.deterministic_converter import deterministic_full_convert
                        det_result = deterministic_full_convert(document_excerpt or "", tid)
                        if det_result.kind != "fallback":
                            if det_result.kind == "noop":
                                yield from _collect_and_yield(iter([
                                    f"Document is already in {tid.upper()} format. No conversion needed."
                                ]))
                            else:
                                yield from _collect_and_yield(iter([
                                    f"Converting to {tid.upper()} format.\n\n" + det_result.edits
                                ]))
                            logger.info("[SmartAgentV2OR][paper=%s] deterministic convert: %s (%s)", paper_id, tid, det_result.kind)
                            break
                        logger.info("[SmartAgentV2OR][paper=%s] deterministic fallback: %s reason=%s", paper_id, tid, det_result.fallback_reason)
                    # Fallback: can't parse document (or flag off) → existing LLM path
                    template_info = "".join(self._handle_apply_template(tid))
                    messages.append(assistant_msg)
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": template_info})
                    continue

                elif tool_name == "review_document":
                    yield self._emit_status("Reviewing document")
                    review_output = "".join(self._format_tool_response(tool_name, tool_args))
                    messages.append(assistant_msg)
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": review_output})
                    continue

                elif tool_name == "list_available_templates":
                    yield self._emit_status("Loading templates")
                    list_output = "".join(self._format_tool_response(tool_name, tool_args))
                    messages.append(assistant_msg)
                    messages.append({"role": "tool", "tool_call_id": tc["id"], "content": list_output})
                    continue

                # Final action tools — hard-branch on answer_question
                if tool_name == "answer_question" and self._answer_was_streamed:
                    # Answer already streamed via _stream_llm_call; response_text has it
                    break
                else:
                    # propose_edit, explain_references, ask_clarification, or
                    # answer_question when arg-live was off/aborted
                    yield from _collect_and_yield(self._format_tool_response(tool_name, tool_args))
                    break
            else:
                # Loop exhausted without break — always inform the user
                fallback = "\n\nI wasn't able to complete the full response. Please try again."
                response_text += fallback
                yield fallback

            # Single store after loop
            self._store_chat_exchange(
                db=db,
                user_id=user_id,
                paper_id=paper_id,
                project_id=project_id,
                user_message=effective_query,
                assistant_message=response_text,
            )

            # Metrics
            ttfb = int((self._first_content_time - t_start) * 1000) if self._first_content_time else -1
            total = int((time.monotonic() - t_start) * 1000)
            logger.info(
                "[SmartAgentV2OR][paper=%s] ttfb_ms=%d total_ms=%d turns=%d tool_calls=%s",
                paper_id, ttfb, total, turn, ",".join(self._last_tools_called) or "none",
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

    _TEMPLATE_LIST_RE = re.compile(
        r"\b(what|which|list|show|available|supported)\b.*\b(template|format|conference|journal)\b"
        r"|\b(template|format|conference|journal)\b.*\b(available|supported|list|options|have)\b",
        re.IGNORECASE,
    )

    def _resolve_tool_choice(self, query: str, turn: int) -> str | dict:
        """Return the tool_choice value for this turn.

        Returns "required", "auto", or a pinned tool_choice dict.
        """
        if turn > 1:
            return "auto"

        q = (query or "").strip().lower()
        if not q:
            return "required"

        # Pin to list_available_templates for template-listing queries
        if self._TEMPLATE_LIST_RE.search(q):
            return {"type": "function", "function": {"name": "list_available_templates"}}

        # Don't force tool_choice for "apply suggestions" follow-ups
        if any(phrase in q for phrase in (
            "apply all suggested changes", "apply suggested changes",
            "apply all suggestions", "apply critical fixes", "apply critical",
        )):
            return "auto"

        return "required"

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
            from datetime import datetime, timedelta, timezone
            from app.models.editor_chat_message import EditorChatMessage

            now = datetime.now(timezone.utc)
            db.add(EditorChatMessage(
                user_id=user_id,
                paper_id=str(paper_id) if paper_id else None,
                project_id=str(project_id) if project_id else None,
                role="user",
                content=user_message,
                created_at=now,
            ))
            db.add(EditorChatMessage(
                user_id=user_id,
                paper_id=str(paper_id) if paper_id else None,
                project_id=str(project_id) if project_id else None,
                role="assistant",
                content=assistant_message,
                created_at=now + timedelta(milliseconds=1),
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

            full_text_count = 0
            lines = [f"({len(refs)} references attached):\n"]
            for i, ref in enumerate(refs, 1):
                authors = ", ".join(ref.authors[:2]) + (" et al." if len(ref.authors) > 2 else "") if ref.authors else "Unknown"
                status_bits = []
                document = getattr(ref, "document", None)
                if document is not None:
                    doc_status = getattr(document.status, "value", None) or str(document.status)
                    if getattr(document, "is_processed_for_ai", False):
                        status_bits.append("full text ready")
                        full_text_count += 1
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

            if full_text_count > 0:
                lines.append(f"\nNote: {full_text_count} paper(s) have full text available. Use search_references to retrieve detailed content from them.")

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error getting reference context: {e}")
            return "[Error loading references — database query failed]"

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
        yield "**NOW call propose_edit** with all necessary edits:\n"
        yield "1. Replace lines 1 through \\maketitle with this template (extract title, authors, affiliations, emails from the current document)\n"
        yield "2. Replace any format-specific environments in the body that the new template does not define (e.g., replace `\\begin{IEEEkeywords}` with `\\begin{keywords}`)\n"


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
