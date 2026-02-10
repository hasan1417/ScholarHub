"""
Smart Agent Service V2 - Tool-based orchestration for LaTeX Editor AI.

Simple approach:
- Templates are in the system prompt (authoritative)
- AI uses propose_edit directly for conversions
- No multi-step tool orchestration needed
"""
import os
import json
import logging
import re
from typing import Optional, Dict, Any, Generator, List, Tuple
from uuid import UUID
from sqlalchemy.orm import Session
from openai import OpenAI

from app.core.config import settings
from app.constants.paper_templates import CONFERENCE_TEMPLATES

logger = logging.getLogger(__name__)


def _is_valid_uuid(val: str) -> bool:
    """Check if string is a valid UUID."""
    try:
        UUID(val)
        return True
    except (ValueError, TypeError):
        return False


def _parse_short_id(url_id: str) -> str | None:
    """Extract short_id from url_id (e.g., 'slug-abc123' -> 'abc123')."""
    if not url_id:
        return None
    parts = url_id.rsplit("-", 1)
    if len(parts) == 2 and re.match(r"^[a-z0-9]{6,12}$", parts[1]):
        return parts[1]
    if re.match(r"^[a-z0-9]{6,12}$", url_id):
        return url_id
    return None


def _resolve_paper_id(db: Session, paper_id: str) -> Optional[UUID]:
    """Resolve paper_id (UUID or slug) to actual UUID."""
    from app.models.research_paper import ResearchPaper

    if _is_valid_uuid(paper_id):
        try:
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == UUID(paper_id)).first()
            if paper:
                return paper.id
        except (ValueError, AttributeError):
            pass

    short_id = _parse_short_id(paper_id)
    if short_id:
        paper = db.query(ResearchPaper).filter(ResearchPaper.short_id == short_id).first()
        if paper:
            return paper.id

    return None


# Tools available to the LaTeX Editor AI
EDITOR_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "answer_question",
            "description": "Answer a question about the paper, its content, structure, or writing. Use this for general questions that don't require editing. Do NOT use for listing templates (use list_available_templates) or reference questions (use explain_references).",
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {
                        "type": "string",
                        "description": "Your answer to the user's question"
                    }
                },
                "required": ["answer"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "ask_clarification",
            "description": "Ask a single clarifying question when the request is too vague to act on. Use only when missing a clear target or operation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "The clarifying question to ask the user"
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-4 short suggested options for quick replies"
                    }
                },
                "required": ["question", "options"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "propose_edit",
            "description": "Propose an edit to the document. Use for any changes: modify, extend, shorten, rewrite, fix, improve, add, remove. NOT for template conversion - use apply_template for that.",
            "parameters": {
                "type": "object",
                "properties": {
                    "explanation": {
                        "type": "string",
                        "description": "Brief explanation of what you're changing and why"
                    },
                    "edits": {
                        "type": "array",
                        "description": "List of edits to make",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {
                                    "type": "string",
                                    "description": "Brief description of this specific edit"
                                },
                                "start_line": {
                                    "type": "integer",
                                    "description": "Line number where the text to replace STARTS"
                                },
                                "end_line": {
                                    "type": "integer",
                                    "description": "Line number where the text to replace ENDS (inclusive)"
                                },
                                "anchor": {
                                    "type": "string",
                                    "description": "First 30-50 characters from start_line (for verification)"
                                },
                                "proposed": {
                                    "type": "string",
                                    "description": "The new VALID LaTeX text"
                                }
                            },
                            "required": ["description", "start_line", "end_line", "anchor", "proposed"]
                        }
                    }
                },
                "required": ["explanation", "edits"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "review_document",
            "description": "Review the document and provide feedback.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Brief overall assessment"},
                    "strengths": {"type": "array", "items": {"type": "string"}},
                    "improvements": {"type": "array", "items": {"type": "string"}},
                    "offer_edits": {"type": "boolean", "description": "Whether to offer to make changes"}
                },
                "required": ["summary", "strengths", "improvements"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_references",
            "description": "Explain or discuss the attached references.",
            "parameters": {
                "type": "object",
                "properties": {
                    "explanation": {"type": "string"},
                    "suggest_discovery": {"type": "boolean", "description": "Suggest using Discovery page for more papers"}
                },
                "required": ["explanation"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_available_templates",
            "description": "List available conference/journal templates. Use ONLY when user asks what formats are available, NOT for conversion.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "apply_template",
            "description": "Convert the document to a specific conference/journal format. Use this when user asks to convert, reformat, or change to a specific format like IEEE, ACL, NeurIPS, CVPR, etc. This will return the template structure, then you MUST call propose_edit to apply it.",
            "parameters": {
                "type": "object",
                "properties": {
                    "template_id": {
                        "type": "string",
                        "enum": list(CONFERENCE_TEMPLATES.keys()),
                        "description": "Target template format"
                    }
                },
                "required": ["template_id"]
            }
        }
    }
]


# System prompt
SYSTEM_PROMPT = """You are an expert academic writing assistant for the LaTeX editor in ScholarHub.

## YOUR CAPABILITIES
- Answer questions about the paper
- Propose edits to any part of the document
- Review and provide feedback
- Convert documents to conference formats

## CLARIFYING QUESTIONS
If the user's request is vague or missing a clear target and operation (e.g., "make it better", "fix this"),
call ask_clarification.
- Ask only ONE question.
- Provide 2-4 short options.
- Do NOT propose edits until clarified.
- If the user responds with "Clarification: ...", do NOT ask another clarification.

## LINE-BASED EDITING
The document shows line numbers like "  15| content here".
Use these EXACT line numbers for start_line and end_line in propose_edit.

## TEMPLATE CONVERSION (TWO-STEP PROCESS)
When user asks to convert (e.g., "convert to ACM", "reformat for IEEE"):
1. FIRST call apply_template with the template_id
2. You will receive the AUTHORITATIVE template structure
3. THEN call propose_edit with ALL necessary edits:
   - Replace lines 1 through \\maketitle with the new preamble
   - Replace any format-specific environments or commands in the document body that are incompatible with the new template (e.g., replace \\begin{IEEEkeywords} with \\begin{keywords})
4. Extract title, authors, affiliations, emails from the CURRENT document and fill into template

IMPORTANT:
- Use apply_template for conversion, NOT list_available_templates
- After apply_template returns, you MUST call propose_edit to apply the changes
- The propose_edit edits array can contain MULTIPLE edits — use one for the preamble and additional ones for body cleanup
- The template preamble ends with \\maketitle — do NOT leave a duplicate \\maketitle in the document
- PRESERVE the existing bibliography format: if the document uses inline \\begin{thebibliography}, keep it (only update \\bibliographystyle). Do NOT replace it with \\bibliography{references}

## REFERENCE SCOPE
You can ONLY discuss or cite references shown in the ATTACHED REFERENCES section.
Do NOT invent, fabricate, or guess reference titles, authors, or findings.
If asked about references not in the attached list, say:
"I can only work with references attached to this paper. Use the Discussion AI or Discovery page to find and add more."

Be concise and helpful. Focus on academic writing quality."""


class SmartAgentServiceV2:
    """
    Tool-based agent for LaTeX Editor AI.
    Templates are in the system prompt - AI uses propose_edit directly.
    """

    FAST_MODEL = "gpt-5-mini"
    QUALITY_MODEL = "gpt-5.2"

    QUALITY_REASONING_EFFORT = "low"
    FULL_REASONING_EFFORT = "high"
    MAX_HISTORY_MESSAGES = 8
    _QUESTION_PREFIXES = ("what", "which", "how", "when", "where", "who", "why")
    _TARGET_TERMS = (
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

    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
        self._current_document = None

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
                model=self.FAST_MODEL,
                messages=messages,
                max_tokens=150,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            logger.warning(f"[SmartAgentV2] Lite execution error: {e}")
            return "Hello! I can help you edit, review, or answer questions about your paper. What would you like to do?"

    def _add_line_numbers(self, text: str) -> str:
        """Add line numbers to text for line-based editing."""
        lines = text.split('\n')
        width = max(len(str(len(lines))), 3)
        numbered_lines = [f"{i:>{width}}| {line}" for i, line in enumerate(lines, 1)]
        return '\n'.join(numbered_lines)

    def stream_query(
        self,
        db: Session,
        user_id: str,
        query: str,
        paper_id: Optional[str] = None,
        project_id: Optional[str] = None,
        document_excerpt: Optional[str] = None,
        reasoning_mode: bool = False,
    ) -> Generator[str, None, None]:
        """Stream a response using tool-based orchestration with multi-turn support."""
        if not self.client:
            yield "AI service not configured."
            return

        # Lite route: greetings, acks, short messages — lightweight LLM, no tools/document
        history_for_route = self._get_recent_history(
            db=db, user_id=user_id, paper_id=paper_id,
            project_id=project_id, limit=4,
        )
        if self._is_lite_route(query, history_for_route):
            lite_response = self._execute_lite(query, history_for_route)
            yield lite_response
            self._store_chat_exchange(
                db=db, user_id=user_id, paper_id=paper_id,
                project_id=project_id, user_message=query,
                assistant_message=lite_response,
            )
            return

        # Store document for template conversion
        self._current_document = document_excerpt

        # Get reference context
        ref_context = self._get_reference_context(db, user_id, paper_id, query)

        # Build context with line numbers
        context_parts = []
        if document_excerpt:
            numbered_doc = self._add_line_numbers(document_excerpt)
            context_parts.append(f"=== USER'S LATEX DOCUMENT (with line numbers) ===\n{numbered_doc}")
        if ref_context:
            context_parts.append(f"=== ATTACHED REFERENCES ===\n{ref_context}")

        full_context = "\n\n".join(context_parts) if context_parts else "No document provided."

        model = self.QUALITY_MODEL
        reasoning_effort = self.FULL_REASONING_EFFORT if reasoning_mode else self.QUALITY_REASONING_EFFORT

        print(f"[SmartAgentV2] Using {model} with reasoning_effort={reasoning_effort}")

        history_messages = self._get_recent_history(
            db=db,
            user_id=user_id,
            paper_id=paper_id,
            project_id=project_id,
            limit=self.MAX_HISTORY_MESSAGES,
        )
        effective_query = self._rewrite_affirmation(query, history_messages) or query

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history_messages)
        messages.append({"role": "user", "content": f"{full_context}\n\n---\n\nUser request: {effective_query}"})
        tools = EDITOR_TOOLS
        if effective_query.strip().lower().startswith("clarification:"):
            tools = [tool for tool in EDITOR_TOOLS if tool["function"]["name"] != "ask_clarification"]

        # Multi-turn for template conversion (apply_template → propose_edit)
        max_turns = 3
        turn = 0

        response_text = ""

        def _collect_and_yield(gen: Generator[str, None, None]) -> Generator[str, None, None]:
            nonlocal response_text
            for chunk in gen:
                response_text += chunk
                yield chunk

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

        try:
            while turn < max_turns:
                turn += 1

                tool_choice = "required" if turn == 1 else "auto"
                if turn == 1 and not self._should_require_tool_choice(effective_query):
                    tool_choice = "auto"

                response = self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    tool_choice=tool_choice,
                    max_completion_tokens=4000,
                    reasoning_effort=reasoning_effort,
                )

                choice = response.choices[0]

                if choice.message.tool_calls:
                    tool_call = choice.message.tool_calls[0]
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    print(f"[SmartAgentV2] Turn {turn}: {tool_name}")

                    # Intermediate tools - return info to AI for further processing
                    if tool_name == "apply_template":
                        tid = tool_args.get("template_id", "")
                        # Deterministic V1: preamble edit in code, body cleanup via LLM
                        if settings.EDITOR_DETERMINISTIC_CONVERT_V1:
                            from app.services.deterministic_converter import deterministic_preamble_convert
                            det_result = deterministic_preamble_convert(document_excerpt or "", tid)
                            if det_result:
                                yield from _collect_and_yield(iter([det_result]))
                                logger.info("[SmartAgentV2][paper=%s] deterministic preamble: %s", paper_id, tid)
                                template_info = "".join(self._handle_apply_template(tid))
                                messages.append(choice.message)
                                messages.append({
                                    "role": "tool",
                                    "tool_call_id": tool_call.id,
                                    "content": template_info + "\n\nIMPORTANT: The preamble (lines 1 through \\maketitle) has ALREADY been converted. Do NOT propose any preamble edits. ONLY call propose_edit if there are body-level cleanups needed (e.g., replace \\begin{IEEEkeywords} with \\begin{keywords}, remove format-specific commands). If no body cleanup is needed, call answer_question to confirm the conversion is complete."
                                })
                                continue
                        # Fallback: existing LLM path
                        template_info = "".join(self._handle_apply_template(tid))
                        messages.append(choice.message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": template_info
                        })
                        continue  # AI will call propose_edit next

                    if tool_name == "review_document":
                        # Intermediate: AI may want to propose_edit after review
                        review_output = "".join(self._format_tool_response(tool_name, tool_args))
                        messages.append(choice.message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": review_output
                        })
                        continue  # Let AI decide if it wants to propose edits

                    if tool_name == "list_available_templates":
                        # Intermediate: AI may want to apply_template next
                        list_output = "".join(self._format_tool_response(tool_name, tool_args))
                        messages.append(choice.message)
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tool_call.id,
                            "content": list_output
                        })
                        continue  # Let AI decide next action

                    # Final action tools - format and return
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
                else:
                    if choice.message.content:
                        response_text = choice.message.content
                        yield choice.message.content
                    else:
                        response_text = "I'm not sure how to help with that. Could you rephrase?"
                        yield response_text
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
            logger.error(f"[SmartAgentV2] Error: {e}")
            yield f"Sorry, an error occurred: {str(e)}"

    def _build_clarification(self, query: str, document_excerpt: Optional[str]) -> Optional[Dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return None
        q_lower = q.lower()
        if q_lower.startswith("clarification:"):
            return None
        if q_lower.endswith("?") and q_lower.split(" ", 1)[0] in self._QUESTION_PREFIXES:
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
        for term in self._TARGET_TERMS:
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
        user_id: str,
        paper_id: Optional[str],
        project_id: Optional[str],
        limit: int = 8,
    ) -> List[Dict[str, str]]:
        try:
            if not paper_id and not project_id:
                return []
            from app.models.editor_chat_message import EditorChatMessage

            query = db.query(EditorChatMessage).filter(EditorChatMessage.user_id == user_id)
            if paper_id:
                query = query.filter(EditorChatMessage.paper_id == str(paper_id))
            elif project_id:
                query = query.filter(EditorChatMessage.project_id == str(project_id))

            rows = (
                query.order_by(EditorChatMessage.created_at.desc())
                .limit(limit)
                .all()
            )
            if not isinstance(rows, list):
                return []

            history = []
            for row in reversed(rows):
                if row.role not in ("user", "assistant"):
                    continue
                content = row.content or ""
                if row.role == "assistant":
                    content = self._sanitize_assistant_content(content)
                    if not content:
                        continue
                history.append({"role": row.role, "content": content})
            return history
        except Exception as e:
            logger.warning(f"[SmartAgentV2] Failed to load editor history: {e}")
            return []

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
        except Exception as e:
            db.rollback()
            logger.warning(f"[SmartAgentV2] Failed to store editor chat: {e}")

    def _format_tool_response(self, tool_name: str, args: Dict[str, Any]) -> Generator[str, None, None]:
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
        max_refs: int = 10
    ) -> str:
        """Get relevant reference summaries for context."""
        try:
            from app.models.reference import Reference
            from app.models.paper_reference import PaperReference

            if paper_id:
                resolved_id = _resolve_paper_id(db, paper_id)
                if not resolved_id:
                    return "Paper not found."

                refs = db.query(Reference).join(
                    PaperReference, PaperReference.reference_id == Reference.id
                ).filter(
                    PaperReference.paper_id == resolved_id
                ).limit(max_refs).all()
            else:
                return ""

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
            logger.error(f"Error getting references: {e}")
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
