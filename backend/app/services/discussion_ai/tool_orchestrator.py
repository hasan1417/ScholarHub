"""
Tool-Based Discussion AI Orchestrator

Uses OpenAI function calling to let the AI decide what context it needs.
Instead of hardcoding what data each skill uses, the AI calls tools on-demand.
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.services.discussion_ai.tools import build_tool_registry
from app.services.discussion_ai.policy import DiscussionPolicy, PolicyDecision
from app.services.discussion_ai.quality_metrics import get_discussion_ai_metrics_collector
from app.services.discussion_ai.utils import filter_duplicate_mutations
from app.services.discussion_ai.mixins import (
    MemoryMixin,
    SearchToolsMixin,
    LibraryToolsMixin,
    AnalysisToolsMixin,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session
    from app.models import Project, ProjectDiscussionChannel, User
    from app.services.ai_service import AIService

logger = logging.getLogger(__name__)

DISCUSSION_TOOL_REGISTRY = build_tool_registry()
# Note: Don't pre-filter tools at module level - filter at runtime based on user role
DISCUSSION_TOOLS = DISCUSSION_TOOL_REGISTRY.get_schema_list()  # Full list for reference

# Tool exposure: all role-permitted tools are sent to the LLM.
# Role-based permissions (permissions.py) handle access control.
# No intent-based filtering — modern models handle 28 tools fine (~5K tokens).

# System prompt with adaptive workflow based on request clarity
BASE_SYSTEM_PROMPT = r"""You are a research assistant helping with academic papers for researchers and scholars.
Prioritize research quality: precision, traceability to sources, and academically rigorous outputs over broad but noisy results.

## SCOPE
You only assist with tasks related to this research project: literature search, paper analysis, academic writing, and project management. If a request is clearly unrelated to research or this project (e.g., personal emails, coding homework, casual chat, creative fiction), briefly explain that you're a research assistant and offer to help with something research-related instead.
Do NOT refuse adjacent requests that could reasonably support research (e.g., explaining a statistical method, summarizing a concept, helping frame a research question, clarifying terminology).

## GOLDEN RULE: ONLY DO WHAT THE USER ASKED

Only call tools that directly address the user's current request. Do NOT proactively call extra tools beyond what was asked — if the user asks to update project info, only update project info. If they ask for papers, search for papers. One request = one action.

Use existing context before searching for new things. If you just searched, discussed, or analyzed papers, those ARE the context. Only search when the user explicitly asks for papers or a search.

When "FOCUSED PAPERS" appear in context → use analyze_across_papers for any question about them.

## PAPER CONTEXT (priority order)

1. **RECENT SEARCH RESULTS** — "first paper", "paper 1", "these papers" refer to the numbered list from the most recent search.
2. **CHANNEL PAPER HISTORY** — "papers we added", "papers from earlier" refer to papers added through this channel (marked with • under "PAPERS ADDED IN THIS CHANNEL").
3. **PROJECT LIBRARY** — "my library", "all my papers" → use get_project_references tool.

If ambiguous, prefer recent search results, then channel history.

## CITATION WORKFLOW

When asked to create a paper or literature review:
1. Check context for papers (search results, channel history)
2. If none → call get_project_references to check library
3. If library is empty → call search_papers first
4. Create paper ONLY after you have papers to cite with \cite{{authorYYYYword}}
5. Every academic paper MUST have \cite{{}} commands. References section is auto-generated — never add it manually.

## DEPTH AWARENESS

- Search results = ABSTRACTS ONLY. Library papers with ingested PDFs = FULL TEXT.
- For content-heavy requests (lit reviews, methodology comparisons): call add_to_library with ingest_pdfs=True FIRST, then write content.
- When asked about a specific paper: check "Papers with FULL TEXT available" in context above. If listed, call get_reference_details BEFORE answering. Only offer to ingest if NOT already in library.
- When user asks a detailed question about a paper WITHOUT full text: answer from the abstract, then offer: "I only have the abstract. Want me to ingest the PDF for deeper analysis?" Do NOT repeat this offer for the same paper.

## SEARCH BEHAVIOR

**Search is ASYNC.** After calling search_papers or batch_search_papers:
- Results appear in the UI as a notification — do NOT list papers in your message.
- Do NOT call get_recent_search_results, update_paper, or create_paper in the same turn.
- Tell the user results will appear, then STOP.

**After a previous search:** If user asks to "create" or "write" something, call get_recent_search_results first to retrieve those papers.

**Vague topics** (e.g., "recent algorithms"): Use discover_topics first, then search specific topics.
**User confirms multiple searches** ("all 6 please", "search all", "yes"): Call batch_search_papers immediately.

Routing, defaults, and filter enforcement are handled by system policy code.
When policy routes to `search_papers`, execute the tool action directly without optional clarification detours.

**Query quality (research-grade):**
- Use concise, high-signal academic queries (typically 4-8 terms).
- Include core concept + context/population + outcome/method when relevant.
- Avoid keyword stuffing, synonym dumping, and raw year lists like "2020 2021 2022 2023".
- If structured year filters are present, do not re-encode them as year keyword spam in query text.

## GUIDELINES

1. Be dynamic and contextual — never ask more than ONE clarifying question
2. Never invent papers from training data — only use search results
3. For general knowledge questions, answer first, then offer to search
4. Output markdown naturally (not in code blocks)
5. For long content, offer to create as a paper instead of dumping in chat
6. Never show UUIDs — use titles and relevant info
7. Always confirm what you created by name
8. When user confirms an action ("yes", "do it", "all") → CALL the tool immediately, don't just respond with text
9. Keep chat responses concise by default. Use at most 8 bullets and avoid long walls of text unless the user explicitly asks for a detailed/full version.

## DATA INTEGRITY
NEVER fabricate statistics, results, percentages, p-values, or specific findings.
If you don't have actual data from a paper (via full text or abstract), say "I'd need the full text for specific numbers."
Only quote findings that appear in the context you have. When summarizing across papers, attribute each finding to its source.

## ACADEMIC WRITING (when creating or updating papers)
- Use formal academic tone — no contractions or colloquialisms
- Use hedging language: "findings suggest", "results indicate", "evidence supports"
- Every factual claim MUST be backed by \cite{{}} — aim for 1-2 citations per paragraph minimum
- Structure sections with clear topic sentences and logical transitions

Project: {project_title} | Channel: {channel_name}
{context_summary}"""

LITE_SYSTEM_PROMPT = """You are a research assistant for the project "{project_title}".
Respond concisely and helpfully. Only assist with research-related tasks for this project.
If the user greets you, greet them back warmly.
If they acknowledge something, confirm briefly. If they ask a research question
or need papers/analysis, let them know you're ready to help and ask what they need.
If a request is clearly unrelated to research, briefly explain you're a research assistant.
Keep responses under 3 sentences for simple exchanges."""

# Reminder injected after conversation history to reinforce key rules
HISTORY_REMINDER = (
    "REMINDER: Use existing context before searching again. "
    "When user confirms an action → call the tool immediately. "
    "Never list papers from memory — only from tool results."
)

# Stage-adaptive hints injected based on AI memory's research_state.stage
STAGE_HINTS = {
    "exploring": "The researcher is exploring broadly. Help narrow the topic, suggest search directions, ask about goals.",
    "refining": "The researcher is refining their scope. Suggest specific comparisons, help formulate concrete research questions.",
    "finding_papers": "The researcher is actively searching. Prioritize search efficiency — suggest batch searches, related papers, semantic search.",
    "analyzing": "The researcher is analyzing papers in depth. Suggest PDF ingestion for full text, offer cross-paper analysis, highlight contradictions.",
    "writing": "The researcher is writing. Focus on citations, section generation, academic tone, structure, and flow.",
}


class ToolOrchestrator(MemoryMixin, SearchToolsMixin, LibraryToolsMixin, AnalysisToolsMixin):
    """
    AI orchestrator that uses tools to gather context dynamically.

    Thread-safe: All request-specific state is passed through method parameters
    or stored in local variables, not instance variables.
    """
    # Safety-net token cap — generous enough to never truncate useful responses.
    # Primary length control is via the system prompt guidance, not this cap.
    DEFAULT_MAX_OUTPUT_TOKENS = 2048

    def __init__(self, ai_service: "AIService", db: "Session"):
        self.ai_service = ai_service
        self.db = db
        self._tool_registry = DISCUSSION_TOOL_REGISTRY
        self._policy = DiscussionPolicy()
        self._quality_metrics = get_discussion_ai_metrics_collector()

    # ── Recent-papers state helpers ─────────────────────────────────────
    # ctx is the turn-time source of truth; Redis is cross-turn persistence.

    @staticmethod
    def _get_recent_papers(ctx: Dict[str, Any]) -> List[Dict]:
        """Single read point for recent search results."""
        return ctx.get("recent_search_results", [])

    @staticmethod
    def _set_recent_papers(
        ctx: Dict[str, Any],
        papers: List[Dict],
        search_id: Optional[str] = None,
    ) -> None:
        """Single write point — updates ctx (turn-time) + Redis (cross-turn)."""
        ctx["recent_search_results"] = papers
        if search_id:
            from app.services.discussion_ai.search_cache import store_search_results
            store_search_results(search_id, papers)

    @property
    def model(self) -> str:
        """Get model from AIService config, with fallback."""
        if hasattr(self.ai_service, 'default_model') and self.ai_service.default_model:
            return self.ai_service.default_model
        return "gpt-5.2"  # Latest OpenAI model (Dec 2025)

    def handle_message(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]] = None,
        recent_search_id: Optional[str] = None,
        previous_state_dict: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        reasoning_mode: bool = False,
        current_user: Optional["User"] = None,
    ) -> Dict[str, Any]:
        """Handle a user message (non-streaming)."""
        from app.services.discussion_ai.route_classifier import classify_route

        try:
            ctx = self._build_request_context(
                project, channel, message, recent_search_results,
                reasoning_mode, conversation_history, current_user,
                recent_search_id=recent_search_id,
            )

            # Classify route
            memory_facts = self._get_ai_memory(channel).get("facts", {})
            route_decision = classify_route(message, conversation_history or [], memory_facts)
            ctx["route"] = route_decision.route
            ctx["route_reason"] = route_decision.reason
            logger.debug(f"[RouteClassifier] route={route_decision.route} reason={route_decision.reason}")

            if route_decision.route == "lite":
                messages = self._build_messages_lite(project, channel, message, conversation_history)
                return self._execute_lite(messages, ctx)

            messages = self._build_messages(project, channel, message, recent_search_results, conversation_history, ctx=ctx)
            return self._execute_with_tools(messages, ctx)

        except Exception as e:
            logger.exception(f"Error in handle_message: {e}")
            return self._error_response(str(e))

    async def handle_message_streaming(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]] = None,
        recent_search_id: Optional[str] = None,
        previous_state_dict: Optional[Dict[str, Any]] = None,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        reasoning_mode: bool = False,
        current_user: Optional["User"] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle a user message with async streaming response.

        Yields:
            dict: Either {"type": "token", "content": "..."} for content tokens,
                  {"type": "status", ...} for tool status updates,
                  or {"type": "result", "data": {...}} at the end with full response.
        """
        from app.services.discussion_ai.route_classifier import classify_route

        try:
            yield {"type": "status", "tool": "", "message": "Understanding your message"}

            ctx = self._build_request_context(
                project,
                channel,
                message,
                recent_search_results,
                reasoning_mode,
                conversation_history,
                current_user,
                recent_search_id=recent_search_id,
            )

            # Classify route
            memory_facts = self._get_ai_memory(channel).get("facts", {})
            route_decision = classify_route(message, conversation_history or [], memory_facts)
            ctx["route"] = route_decision.route
            ctx["route_reason"] = route_decision.reason
            logger.debug(f"[RouteClassifier] route={route_decision.route} reason={route_decision.reason}")

            if route_decision.route == "lite":
                messages = self._build_messages_lite(project, channel, message, conversation_history)
                async for event in self._execute_lite_streaming(messages, ctx):
                    yield event
                return

            messages = self._build_messages(project, channel, message, recent_search_results, conversation_history, ctx=ctx)

            async for event in self._execute_with_tools_streaming(messages, ctx):
                yield event

        except Exception as e:
            logger.exception(f"Error in handle_message_streaming: {e}")
            yield {"type": "result", "data": self._error_response(str(e))}

    def _get_user_role_for_project(
        self,
        project: "Project",
        user: Optional["User"],
    ) -> tuple[str, bool]:
        """Get user's role and owner status for a project.

        Returns:
            (role: str, is_owner: bool) - role is normalized to 'viewer', 'editor', or 'admin'
        """
        from app.models import ProjectMember
        from app.services.discussion_ai.tools.permissions import normalize_role

        if user is None:
            return ("viewer", False)

        # Check if user is project creator (owner)
        is_owner = project.created_by == user.id
        if is_owner:
            return ("admin", True)

        # Look up membership
        membership = (
            self.db.query(ProjectMember)
            .filter(
                ProjectMember.project_id == project.id,
                ProjectMember.user_id == user.id,
                ProjectMember.status == "accepted",
            )
            .first()
        )

        if membership:
            return (normalize_role(membership.role), False)

        # No membership found - fail closed
        return ("viewer", False)

    def _build_request_context(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]],
        reasoning_mode: bool,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        current_user: Optional["User"] = None,
        recent_search_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build thread-safe request context."""
        import re

        # Extract count from message (e.g., "find 5 papers" → 5)
        count_match = re.search(r"(\d+)\s*(?:papers?|references?|articles?)", message, re.IGNORECASE)
        extracted_count = int(count_match.group(1)) if count_match else None

        # Get user's role and owner status for permission checks
        user_role, is_owner = self._get_user_role_for_project(project, current_user)
        logger.debug(f"[Permission] User role: {user_role}, is_owner: {is_owner}, user: {current_user.id if current_user else 'None'}")

        return {
            "project": project,
            "channel": channel,
            "current_user": current_user,  # User who sent the prompt
            "user_role": user_role,  # Normalized role for permission checks
            "is_owner": is_owner,  # Explicit owner flag
            "recent_search_results": recent_search_results or [],
            "recent_search_id": recent_search_id,
            "reasoning_mode": reasoning_mode,
            "max_papers": extracted_count if extracted_count else 999,
            "papers_requested": 0,
            "user_message": message,  # Store for memory update
            "conversation_history": conversation_history or [],  # Store for memory update
        }

    def _build_messages(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        recent_search_results: Optional[List[Dict]],
        conversation_history: Optional[List[Dict[str, str]]],
        ctx: Optional[Dict[str, Any]] = None,
    ) -> List[Dict]:
        """Build the messages array for the LLM with smart token-based context management."""
        from app.services.discussion_ai.token_utils import (
            count_tokens,
            count_message_tokens,
            fit_messages_in_budget,
            get_available_context,
        )

        context_summary = self._build_context_summary(project, channel, recent_search_results)

        # Build memory context from AI memory (summary + facts)
        current_user = ctx.get("current_user") if ctx else None
        current_user_id = getattr(current_user, "id", None)
        memory_context = self._build_memory_context(channel, user_id=current_user_id)

        # Combine context and memory
        full_context = context_summary
        if memory_context:
            full_context = f"{context_summary}\n\n{memory_context}"
            logger.info(f"Memory context added to prompt. Length: {len(memory_context)}")
            if "FOCUSED PAPERS" in memory_context:
                logger.info("✅ FOCUSED PAPERS section is in the context!")
            else:
                logger.info("❌ FOCUSED PAPERS section NOT in the context")

        system_prompt = BASE_SYSTEM_PROMPT.format(
            project_title=project.title,
            channel_name=channel.name,
            context_summary=full_context,
        )

        # Inject stage-adaptive hint from AI memory
        memory_dict = self._get_ai_memory(channel)
        research_stage = memory_dict.get("research_state", {}).get("stage", "exploring")
        stage_hint = STAGE_HINTS.get(research_stage, "")
        if stage_hint:
            system_prompt += f"\n\n## CURRENT RESEARCH STAGE: {research_stage}\n{stage_hint}"

        # Inject formal research question if available
        research_question = memory_dict.get("facts", {}).get("research_question")
        if research_question:
            system_prompt += f"\nThe researcher's question: \"{research_question}\" — tailor suggestions to this."

        clarification_guardrail = self._build_clarification_guardrail(memory_dict, message)
        if clarification_guardrail:
            system_prompt += f"\n\n## CLARIFICATION POLICY\n{clarification_guardrail}"
            logger.info("[ClarificationGuardrail] Applied deterministic no-repeat clarification rule.")

        system_prompt += (
            "\n\n## RESPONSE FORMAT\n"
            "Use Markdown formatting: **bold** for key terms, `code` for technical identifiers, "
            "## headings for sections when structuring longer answers. Use numbered lists (1.) and "
            "bullet points (-) for structured content.\n\n"
            "Match response length to the question complexity:\n"
            "- Quick follow-ups, confirmations, and simple questions: 2-4 sentences.\n"
            "- Research framing, methodology advice, and new topic exploration: structured detail is fine.\n"
            "- After a search tool returns results: keep commentary brief, the results speak for themselves.\n"
            "Always end with one concrete next step. Avoid repeating information already shown in the conversation."
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Add role-based permission notice for viewers (read-only tool access).
        user_role = ctx.get("user_role") if ctx else None
        if user_role == "viewer":
            viewer_notice = """
CRITICAL - VIEWER ACCESS (READ-ONLY):
You are assisting a VIEWER of this project.

Viewers can use read-only tools (for example: search and analysis) but cannot use write/admin actions.
Never claim to create, update, or modify project/library content for a viewer.
If asked to perform write actions, explain that editor/admin access is required."""
            messages.append({"role": "system", "content": viewer_notice})

        # Calculate tokens used by system messages
        system_tokens = sum(count_message_tokens(m, self.model) for m in messages)
        user_message_tokens = count_tokens(message, self.model) + 4  # +4 for message overhead

        logger.debug(f"[TokenContext] System prompt: {system_tokens} tokens, User message: {user_message_tokens} tokens")

        # Add conversation history with TOKEN-BASED windowing
        if conversation_history:
            # Calculate available budget for history
            # Use model-aware context limits with reserves for response and tools
            available_for_history = get_available_context(
                self.model,
                system_tokens=system_tokens + user_message_tokens,
                reserve_for_response=True,
                reserve_for_tools=True,
            )

            # Cap at our explicit budget to prevent runaway context
            history_budget = min(available_for_history, self.CONVERSATION_HISTORY_TOKEN_BUDGET)

            # Apply count-based cap first (SLIDING_WINDOW_SIZE), then fit by tokens
            capped_history = conversation_history
            if len(capped_history) > self.SLIDING_WINDOW_SIZE:
                capped_history = capped_history[-self.SLIDING_WINDOW_SIZE:]

            # Fit messages within budget (keeping newest)
            fitted_messages, tokens_used = fit_messages_in_budget(
                capped_history,
                budget=history_budget,
                model=self.model,
                keep_newest=True,
            )

            logger.debug(
                f"[TokenContext] History: {len(fitted_messages)}/{len(conversation_history)} messages, "
                f"{tokens_used}/{history_budget} tokens"
            )

            for msg in fitted_messages:
                messages.append({"role": msg["role"], "content": msg["content"]})

            # Add reminder after history to override old patterns
            if fitted_messages:
                messages.append({"role": "system", "content": HISTORY_REMINDER})

        messages.append({"role": "user", "content": message})
        return messages

    def _build_messages_lite(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        conversation_history: Optional[List[Dict[str, str]]],
    ) -> List[Dict]:
        """Build a minimal messages array for lite route (no tools, no context summary)."""
        system_prompt = LITE_SYSTEM_PROMPT.format(project_title=project.title)
        messages: List[Dict] = [{"role": "system", "content": system_prompt}]
        # Include only last 4 messages for coherence
        if conversation_history:
            for msg in conversation_history[-4:]:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})
        return messages

    def _error_response(self, error_msg: str = "") -> Dict[str, Any]:
        """Build a standard error response."""
        return {
            "message": "I'm sorry, I encountered an error while processing your request. Please try again.",
            "actions": [],
            "citations": [],
            "model_used": self.model,
            "reasoning_used": False,
            "tools_called": [],
            "conversation_state": {},
        }

    def _get_model_output_token_cap(self, ctx: Dict[str, Any]) -> int:
        """Token cap used by provider clients as a safety net for response length."""
        return self.DEFAULT_MAX_OUTPUT_TOKENS

    def _generate_content_fallback(
        self,
        ctx: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Optional subclass hook for generating fallback text when model output is empty."""
        return None

    def _build_empty_response_fallback(self, ctx: Dict[str, Any]) -> str:
        """Deterministic, context-aware fallback when model returns empty/cut-off text."""
        user_message = (ctx.get("user_message") or "").strip()
        rq_match = re.search(r"research question is:\s*(.+)$", user_message, re.IGNORECASE)
        if rq_match:
            rq = rq_match.group(1).strip().rstrip(" .")
            return (
                f"I captured your research question: \"{rq}\". "
                "Next step: tell me whether to search recent papers now or narrow the scope first."
            )
        if user_message:
            preview = user_message[:180].rstrip(" .")
            return (
                f"I captured your request: \"{preview}\". "
                "Next step: tell me whether to search papers, refine scope, or draft a concrete plan."
            )
        return (
            "I captured your request. "
            "Next step: tell me whether to search papers, refine scope, or draft a concrete plan."
        )

    def _build_search_completion_message(self, ctx: Dict[str, Any], tool_results: List[Dict[str, Any]]) -> Optional[str]:
        """Deterministic short response after successful search tool execution."""
        search_results = [
            tr for tr in tool_results
            if tr.get("name") in ("search_papers", "batch_search_papers")
        ]
        if not search_results:
            return None

        if any((tr.get("result") or {}).get("status") == "error" for tr in search_results):
            return None

        return "Searching for papers now. Results will appear in the UI shortly."

    def _generate_tool_summary_message(self, tool_results: List[Dict[str, Any]]) -> str:
        """Generate deterministic fallback text when model returns empty content."""
        for tr in tool_results:
            name = tr.get("name", "")
            result = tr.get("result", {}) or {}
            if name in ("search_papers", "batch_search_papers"):
                if result.get("status") == "error":
                    return "Search failed due to a temporary issue. Please retry."
                return "Searching for papers now. Results will appear in the UI shortly."

        tools_called = [tr.get("name", "tool") for tr in tool_results]
        if not tools_called:
            return ""
        return f"Completed: {', '.join(tools_called)}."

    def _apply_response_budget(
        self,
        text: str,
        ctx: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> str:
        """Minimal response post-processing — no truncation, no rewriting.

        Only replaces verbose text with a short confirmation after a successful
        async search (results appear in UI, so repeating them is noise).
        """
        # Search confirmation takes priority — results appear in UI separately,
        # so always use the short message regardless of what the model said.
        search_short_message = self._build_search_completion_message(ctx, tool_results)
        if search_short_message:
            return search_short_message

        return text

    def _get_tool_status_message(self, tool_name: str) -> str:
        """Return a human-readable status message for a tool being called."""
        tool_messages = {
            "get_recent_search_results": "Reviewing search results",
            "get_project_references": "Checking your library",
            "get_reference_details": "Reading paper details",
            "analyze_reference": "Analyzing paper content",
            "search_papers": "Searching for papers",
            "get_project_papers": "Loading your drafts",
            "get_project_info": "Getting project info",
            "get_channel_resources": "Checking channel resources",
            "create_paper": "Creating paper",
            "update_paper": "Updating paper",
            "create_artifact": "Generating document",
            "discover_topics": "Discovering topics",
            "batch_search_papers": "Searching multiple topics",
            "add_to_library": "Adding papers to library & ingesting PDFs",
            "update_project_info": "Updating project info",
            # Search UI & paper focus tools
            "trigger_search_ui": "Opening search interface",
            "focus_on_papers": "Loading papers into focus",
            "analyze_across_papers": "Analyzing across focused papers",
            "generate_section_from_discussion": "Generating section from discussion",
            # New researcher tooling
            "export_citations": "Exporting citations",
            "compare_papers": "Comparing papers",
            "suggest_research_gaps": "Analyzing research gaps",
            "generate_abstract": "Generating abstract",
            "annotate_reference": "Annotating reference",
        }
        return tool_messages.get(tool_name, "Processing")

    def _execute_with_tools(
        self,
        messages: List[Dict],
        ctx: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Execute with tool calling (non-streaming)."""
        try:  # noqa: SIM117
            conversation_history = ctx.get("conversation_history")
            policy_decision = self._classify_and_build_policy(ctx, conversation_history)
            t_start = time.monotonic()
            mutating_calls_seen: set = set()

            max_iterations = 8
            iteration = 0
            all_tool_results = []
            response = {"content": "", "tool_calls": []}
            clarification_first_detected = False
            search_tool_executed = False

            while iteration < max_iterations:
                iteration += 1
                logger.info(f"Tool orchestrator iteration {iteration}")

                response = self._call_ai_with_tools(messages, ctx)
                tool_calls = response.get("tool_calls", [])

                if not tool_calls:
                    # Deterministic fallback: if direct-search intent has not produced a search tool
                    # call yet, force search before returning any clarification text.
                    if (
                        policy_decision.should_force_tool("search_papers")
                        and policy_decision.search is not None
                        and not search_tool_executed
                    ):
                        clarification_first_detected = clarification_first_detected or bool((response.get("content") or "").strip())
                        forced_query = policy_decision.search.query or self._build_fallback_search_query(ctx)
                        forced_tool_call = {
                            "id": "forced-search-1",
                            "name": "search_papers",
                            "arguments": {
                                "query": forced_query,
                                "count": policy_decision.search.count,
                                "limit": policy_decision.search.count,
                                "open_access_only": policy_decision.search.open_access_only,
                                "year_from": policy_decision.search.year_from,
                                "year_to": policy_decision.search.year_to,
                            },
                        }
                        logger.info(f"Applying direct-search fallback with query: {forced_query[:120]}")
                        forced_results = self._execute_tool_calls([forced_tool_call], ctx)
                        all_tool_results.extend(forced_results)
                        search_tool_executed = True
                    break

                # Filter out duplicate mutating tool calls
                tool_calls = filter_duplicate_mutations(tool_calls, mutating_calls_seen)

                if not tool_calls:
                    # All tool calls were duplicates — treat as final iteration
                    break

                # Execute tool calls
                tool_results = self._execute_tool_calls(tool_calls, ctx)
                all_tool_results.extend(tool_results)
                if any(tr.get("name") in ("search_papers", "batch_search_papers") for tr in tool_results):
                    search_tool_executed = True

                # If only search tools ran, skip re-querying the model — the response
                # will be the short confirmation from _apply_response_budget anyway.
                search_only = all(
                    tr.get("name") in ("search_papers", "batch_search_papers")
                    for tr in tool_results
                )
                if search_only and search_tool_executed:
                    break

                # Add assistant message with tool calls
                formatted_tool_calls = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"]),
                        }
                    }
                    for tc in tool_calls
                ]

                messages.append({
                    "role": "assistant",
                    "content": response.get("content") or "",
                    "tool_calls": formatted_tool_calls,
                })

                # Add tool results
                for tool_call, result in zip(tool_calls, tool_results):
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "content": json.dumps(result, default=str),
                    })

            final_message = response.get("content", "")
            if not final_message.strip() and all_tool_results:
                final_message = self._generate_tool_summary_message(all_tool_results)
            final_message = self._apply_response_budget(final_message, ctx, all_tool_results)
            if not final_message.strip():
                fallback = self._generate_content_fallback(ctx, all_tool_results)
                if fallback and fallback.strip():
                    final_message = fallback.strip()
            if not final_message.strip():
                final_message = self._build_empty_response_fallback(ctx)
            actions = self._extract_actions(final_message, all_tool_results)

            # Update AI memory after successful response
            contradiction_warning = None
            try:
                contradiction_warning = self.update_memory_after_exchange(
                    ctx["channel"],
                    ctx["user_message"],
                    final_message,
                    ctx.get("conversation_history", []),
                    user_id=getattr(ctx.get("current_user"), "id", None),
                )
                if contradiction_warning:
                    logger.info(f"Contradiction detected: {contradiction_warning}")
            except Exception as mem_err:
                logger.error(f"Failed to update AI memory: {mem_err}")

            # Deterministic stage transition after successful search tools.
            stage_transition_success = self._enforce_finding_papers_stage_after_search(ctx, all_tool_results)
            self._record_quality_metrics(ctx, policy_decision, all_tool_results, clarification_first_detected, stage_transition_success)

            # Persist _last_tools_called for route classifier follow-up detection
            tools_called = [t["name"] for t in all_tool_results] if all_tool_results else []
            try:
                channel = ctx.get("channel")
                if channel:
                    memory = self._get_ai_memory(channel)
                    memory.setdefault("facts", {})["_last_tools_called"] = tools_called
                    self._save_ai_memory(channel, memory)
            except Exception as exc:
                logger.debug("Failed to persist _last_tools_called: %s", exc)

            total_ms = int((time.monotonic() - t_start) * 1000)
            logger.info(
                "[TurnMetrics] route=full tools_count=%d total_ms=%d model=%s",
                len(all_tool_results), total_ms, self.model,
            )

            return {
                "message": final_message,
                "actions": actions,
                "citations": [],
                "model_used": self.model,
                "reasoning_used": ctx.get("reasoning_mode", False),
                "tools_called": tools_called,
                "conversation_state": {},
                "memory_warning": contradiction_warning,  # Include contradiction warning
            }

        except Exception as e:
            logger.exception(f"Error in _execute_with_tools: {e}")
            return self._error_response(str(e))

    def _is_direct_paper_search_request(self, user_message: str) -> bool:
        """Return True if user explicitly asks to search/find papers now."""
        return self._policy.is_direct_paper_search_request(user_message)

    def _is_tool_available_for_ctx(self, ctx: Dict[str, Any], tool_name: str) -> bool:
        """Check whether a tool is available to the current user role/context.

        Role-only check (avoids chicken-and-egg with policy needing tool availability).
        """
        from app.services.discussion_ai.tools.permissions import can_use_tool
        return can_use_tool(tool_name, ctx.get("user_role", "viewer"), ctx.get("is_owner", False))

    def _build_fallback_search_query(self, ctx: Dict[str, Any]) -> str:
        """Build a reasonable fallback query for forced direct-search routing."""
        user_message = (ctx.get("user_message") or "").strip()
        topic_hint = ""
        last_search_topic = ""

        channel = ctx.get("channel")
        if channel:
            try:
                memory = self._get_ai_memory(channel)
                facts = memory.get("facts", {}) if isinstance(memory, dict) else {}
                topic_hint = (
                    (facts.get("research_topic") or "").strip()
                    or (facts.get("research_question") or "").strip()
                )
                search_state = memory.get("search_state", {}) if isinstance(memory, dict) else {}
                last_search_topic = (search_state.get("last_effective_topic") or "").strip()
            except Exception:
                topic_hint = ""
                last_search_topic = ""

        project_context = self._build_project_context(ctx)
        return self._policy.build_search_query(
            user_message=user_message,
            topic_hint=topic_hint,
            last_search_topic=last_search_topic,
            project_context=project_context,
            derive_topic_fn=self._derive_research_topic_from_text,
        )

    def _user_requested_open_access(self, user_message: str) -> bool:
        """Return True if user explicitly requests OA/PDF-only results."""
        return self._policy.user_requested_open_access(user_message)

    def _user_requested_count(self, user_message: str) -> bool:
        """Return True if user explicitly asks for a specific number of papers."""
        return self._extract_requested_paper_count(user_message) is not None

    def _extract_requested_paper_count(self, user_message: str) -> Optional[int]:
        """Extract explicit requested paper count from user text."""
        return self._policy.extract_requested_paper_count(user_message)

    def _build_project_context(self, ctx: Dict[str, Any]) -> str:
        """Build project context string (keywords + title) for search resolution."""
        project = ctx.get("project")
        if not project:
            return ""
        parts = []
        keywords = getattr(project, "keywords", None)
        if keywords:
            if isinstance(keywords, list):
                parts.append(", ".join(str(k).strip() for k in keywords if k))
            else:
                parts.append(str(keywords).strip())
        if getattr(project, "title", None):
            title = project.title.strip()
            # Only add title if it contributes new info beyond keywords
            if not parts or title.lower() not in parts[0].lower():
                parts.append(title)
        return ", ".join(parts)[:300] if parts else ""

    def _build_policy_decision(self, ctx: Dict[str, Any]) -> PolicyDecision:
        """Build deterministic policy decision for current user turn."""
        topic_hint = ""
        last_search_topic = ""
        channel = ctx.get("channel")
        if channel:
            try:
                memory = self._get_ai_memory(channel)
                facts = memory.get("facts", {}) if isinstance(memory, dict) else {}
                topic_hint = (
                    (facts.get("research_topic") or "").strip()
                    or (facts.get("research_question") or "").strip()
                )
                search_state = memory.get("search_state", {}) if isinstance(memory, dict) else {}
                last_search_topic = (search_state.get("last_effective_topic") or "").strip()
            except Exception:
                topic_hint = ""
                last_search_topic = ""

        project_context = self._build_project_context(ctx)

        decision = self._policy.build_decision(
            user_message=ctx.get("user_message", ""),
            topic_hint=topic_hint,
            last_search_topic=last_search_topic,
            project_context=project_context,
            search_tool_available=self._is_tool_available_for_ctx(ctx, "search_papers"),
            derive_topic_fn=self._derive_research_topic_from_text,
        )
        try:
            logger.info(
                "[PolicyDecision] %s",
                json.dumps(
                    {
                        "intent": decision.intent,
                        "force_tool": decision.force_tool,
                        "reasons": decision.reasons,
                        "search": {
                            "query": decision.search.query if decision.search else None,
                            "count": decision.search.count if decision.search else None,
                            "open_access_only": decision.search.open_access_only if decision.search else None,
                            "year_from": decision.search.year_from if decision.search else None,
                            "year_to": decision.search.year_to if decision.search else None,
                        },
                        "action_plan": {
                            "primary_tool": decision.action_plan.primary_tool if decision.action_plan else None,
                            "force_tool": decision.action_plan.force_tool if decision.action_plan else None,
                            "blocked_tools": list(decision.action_plan.blocked_tools) if decision.action_plan else [],
                        },
                    }
                ),
            )
        except Exception:
            logger.info("[PolicyDecision] intent=%s force_tool=%s", decision.intent, decision.force_tool)
        return decision

    @staticmethod
    def _infer_update_mode_from_message(user_message: str) -> str:
        msg = (user_message or "").lower()
        if any(token in msg for token in ("remove", "delete", "drop")):
            return "remove"
        if any(token in msg for token in ("add", "append", "also include", "include too", "plus")):
            return "append"
        return "replace"

    def _is_tool_blocked_by_policy(
        self,
        tool_name: str,
        policy_decision: Optional[PolicyDecision],
    ) -> bool:
        if not isinstance(policy_decision, PolicyDecision):
            return False
        action_plan = policy_decision.action_plan
        if not action_plan:
            return False
        return tool_name in set(action_plan.blocked_tools or ())

    def _normalize_tool_arguments(
        self,
        tool_name: str,
        args: Dict[str, Any],
        ctx: Dict[str, Any],
        policy_decision: Optional[PolicyDecision],
    ) -> Dict[str, Any]:
        normalized = dict(args or {})

        # Structural overrides apply whenever search_papers is called,
        # regardless of whether the policy detected direct_search intent.
        # The model decides WHEN to search (it generalizes well).
        # Deterministic extraction decides HOW (count, year, OA — reliable via regex).
        if tool_name == "search_papers":
            user_msg = ctx.get("user_message", "")
            has_policy_search = (
                isinstance(policy_decision, PolicyDecision)
                and policy_decision.search is not None
            )

            # Count: policy > user extraction > model > default 5
            if has_policy_search:
                normalized["count"] = policy_decision.search.count
            else:
                requested_count = self._extract_requested_paper_count(user_msg)
                normalized["count"] = requested_count if requested_count is not None else (args.get("count") or 5)
            normalized["limit"] = normalized["count"]

            # OA: policy > user extraction > model
            if has_policy_search:
                normalized["open_access_only"] = policy_decision.search.open_access_only
            else:
                normalized["open_access_only"] = self._user_requested_open_access(user_msg) or args.get("open_access_only", False)

            # Year bounds: policy > user extraction > model
            if has_policy_search and (policy_decision.search.year_from or policy_decision.search.year_to):
                normalized["year_from"] = policy_decision.search.year_from
                normalized["year_to"] = policy_decision.search.year_to
            else:
                year_from, year_to = self._policy.extract_year_bounds(user_msg)
                normalized["year_from"] = year_from or args.get("year_from")
                normalized["year_to"] = year_to or args.get("year_to")

            # Query: when the user explicitly asked to search, prefer the
            # policy-extracted topic (user's own words) so that the downstream
            # understand_query() receives clean input instead of model keyword
            # soup.  When the model autonomously decided to search (no policy
            # search detected), the model query is the only signal available.
            model_query = (args.get("query") or "").strip()
            policy_query = policy_decision.search.query if has_policy_search else ""
            if has_policy_search and policy_query and not self._policy.is_low_information_query(policy_query):
                normalized["query"] = policy_query
            elif model_query and not self._policy.is_low_information_query(model_query):
                normalized["query"] = model_query
            else:
                normalized["query"] = self._build_fallback_search_query(ctx)

            # Log
            query_source = "model" if normalized.get("query") == model_query and model_query else "policy"
            logger.info(
                "[SearchArgs] %s",
                json.dumps(
                    {
                        "query": normalized.get("query"),
                        "query_source": query_source,
                        "model_query": model_query if model_query != normalized.get("query") else None,
                        "count": normalized.get("count"),
                        "limit": normalized.get("limit"),
                        "open_access_only": normalized.get("open_access_only"),
                        "year_from": normalized.get("year_from"),
                        "year_to": normalized.get("year_to"),
                    }
                ),
            )

        # Deterministic update mode inference when model omits/guesses modes.
        if tool_name == "update_project_info":
            inferred_mode = self._infer_update_mode_from_message(ctx.get("user_message", ""))
            if normalized.get("objectives") is not None and not normalized.get("objectives_mode"):
                normalized["objectives_mode"] = inferred_mode
            if normalized.get("keywords") is not None and not normalized.get("keywords_mode"):
                normalized["keywords_mode"] = inferred_mode

        return normalized

    def _persist_last_effective_search_topic(
        self,
        ctx: Dict[str, Any],
        tool_name: str,
        args: Dict[str, Any],
        result: Dict[str, Any],
    ) -> None:
        if tool_name not in ("search_papers", "batch_search_papers"):
            return
        if not isinstance(result, dict):
            return
        if result.get("status") == "error":
            return
        channel = ctx.get("channel")
        if channel is None:
            return

        query = (args.get("query") or "").strip()
        if not query:
            return
        try:
            memory = self._get_ai_memory(channel)
            search_state = memory.get("search_state", {})
            search_state["last_effective_topic"] = query[:300]
            search_state["last_count"] = int(args.get("count") or args.get("limit") or 0)
            search_state["last_updated_at"] = datetime.now(timezone.utc).isoformat()
            memory["search_state"] = search_state
            self._save_ai_memory(channel, memory)
        except Exception as exc:
            logger.debug("Failed to persist last effective search topic: %s", exc)

    def _build_context_summary(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        recent_search_results: Optional[List[Dict]],
    ) -> str:
        """Build a lightweight summary of available context."""
        lines = []

        # Project info - always include so AI knows the context
        lines.append("## Project Overview")
        lines.append(f"**Title:** {project.title or 'Untitled Project'}")
        if project.idea:
            # Truncate long descriptions
            idea_preview = project.idea[:500] + "..." if len(project.idea) > 500 else project.idea
            lines.append(f"**Description:** {idea_preview}")
        if project.scope:
            lines.append(f"**Objectives:** {project.scope}")
        if project.keywords:
            lines.append(f"**Keywords:** {project.keywords}")
        lines.append("")  # Empty line separator

        ref_count = 0
        paper_count = 0
        resource_count = 0

        # Database-dependent sections - wrapped to handle non-SQLAlchemy test DBs
        try:
            from app.models import (
                ProjectReference, ResearchPaper, Reference,
                ProjectDiscussionChannelResource, ProjectDiscussionTask,
            )

            # Discussion tasks - show open and in-progress tasks
            active_tasks = self.db.query(ProjectDiscussionTask).filter(
                ProjectDiscussionTask.project_id == project.id,
                ProjectDiscussionTask.status.in_(["open", "in_progress"])
            ).order_by(ProjectDiscussionTask.created_at.desc()).limit(10).all()

            if active_tasks:
                lines.append("## Active Tasks")
                for task in active_tasks:
                    status_icon = "🔄" if task.status == "in_progress" else "📋"
                    due_str = f" (due: {task.due_date.strftime('%Y-%m-%d')})" if task.due_date else ""
                    lines.append(f"- {status_icon} **{task.title}**{due_str}")
                    if task.description:
                        desc_preview = task.description[:100] + "..." if len(task.description) > 100 else task.description
                        lines.append(f"  {desc_preview}")
                lines.append("")  # Empty line separator

            lines.append("## Available Resources")

            # Get project references with full text info using JOIN (optimized - single query)
            refs_with_status = self.db.query(Reference.id, Reference.title, Reference.status).join(
                ProjectReference, ProjectReference.reference_id == Reference.id
            ).filter(ProjectReference.project_id == project.id).limit(1000).all()

            ref_count = len(refs_with_status)
            if ref_count > 0:
                ingested_refs = [(r.id, r.title) for r in refs_with_status if r.status in ("ingested", "analyzed")]
                lines.append(f"- Project library: {ref_count} saved references ({len(ingested_refs)} with full text)")
                if ingested_refs:
                    lines.append("  **Papers with FULL TEXT available** - USE get_reference_details(reference_id) to read:")
                    for ref_id, title in ingested_refs[:5]:
                        title_preview = (title[:50] if title else "Untitled")
                        lines.append(f"    . {title_preview}... (reference_id: {ref_id})")

            # Count project papers
            paper_count = self.db.query(ResearchPaper).filter(
                ResearchPaper.project_id == project.id
            ).count()
            if paper_count > 0:
                lines.append(f"- Project papers: {paper_count} drafts")

        except (AttributeError, Exception) as e:
            logger.debug(f"Context summary DB queries skipped: {e}")
            lines.append("## Available Resources")

        # Recent search results - show prominently
        if recent_search_results:
            lines.append(f"\n**RECENT SEARCH RESULTS** (user's 'first paper', 'paper 2', etc. refer to these!):")
            for i, p in enumerate(recent_search_results, 1):
                title = p.get("title", "Untitled")[:80]
                year = p.get("year", "")
                authors = p.get("authors", "")
                if isinstance(authors, list):
                    authors = ", ".join(authors[:2]) + ("..." if len(authors) > 2 else "")
                lines.append(f"  {i}. \"{title}{'...' if len(p.get('title', '')) > 80 else ''}\" ({authors}, {year})")

        try:
            from app.models import ProjectReference, Reference, ProjectDiscussionChannelResource

            # Papers added through this channel (optimized JOIN query)
            channel_papers = self.db.query(
                Reference.id, Reference.title, Reference.year, Reference.status,
                ProjectReference.annotations,
            ).join(
                ProjectReference, ProjectReference.reference_id == Reference.id
            ).filter(
                ProjectReference.project_id == project.id,
                ProjectReference.added_via_channel_id == channel.id
            ).limit(20).all()

            if channel_papers:
                lines.append(f"\n**PAPERS ADDED IN THIS CHANNEL** ({len(channel_papers)} papers discussed/added here):")
                for ref in channel_papers:
                    title = (ref.title[:60] if ref.title else "Untitled")
                    ft_marker = " [FULL TEXT]" if ref.status in ("ingested", "analyzed") else ""
                    tags_str = ""
                    if ref.annotations and ref.annotations.get("tags"):
                        tags_str = f" [tags: {', '.join(ref.annotations['tags'])}]"
                    lines.append(f"  . \"{title}...\" ({ref.year or 'n/a'}){ft_marker}{tags_str} - ref_id: {ref.id}")
                lines.append("  -> User can refer to these as 'papers we added', 'papers from earlier'")

            # Channel resources
            resource_count = self.db.query(ProjectDiscussionChannelResource).filter(
                ProjectDiscussionChannelResource.channel_id == channel.id
            ).count()
            if resource_count > 0:
                lines.append(f"- Channel resources: {resource_count} attached")
        except (AttributeError, Exception) as e:
            logger.debug(f"Context summary channel queries skipped: {e}")

        # If no resources at all, add a note
        if ref_count == 0 and paper_count == 0 and not recent_search_results and resource_count == 0:
            lines.append("- No papers or references loaded yet")

        return "\n".join(lines)

    def _get_classifier_client(self):
        """Return sync client for the intent classifier. Subclasses may override."""
        return getattr(self, "openrouter_client", None)

    def _classify_and_build_policy(
        self,
        ctx: Dict[str, Any],
        conversation_history: Optional[List[Dict]] = None,
    ) -> PolicyDecision:
        """Build deterministic policy (search params, project update).

        No LLM classifier — all role-permitted tools are always available.
        """
        policy = self._build_policy_decision(ctx)
        ctx["policy_decision"] = policy
        logger.info("[Policy] intent=%s reasons=%s", policy.intent, policy.reasons)
        return policy

    def _get_tools_for_context(self, ctx: Dict[str, Any]) -> List[Dict]:
        """Get all tools the user's role permits."""
        user_role = ctx.get("user_role", "viewer")
        is_owner = ctx.get("is_owner", False)
        return DISCUSSION_TOOL_REGISTRY.get_schema_list_for_role(user_role, is_owner)

    def _get_tools_for_user(self, ctx: Dict[str, Any]) -> List[Dict]:
        """Get tools filtered by intent + user role (backward compat wrapper)."""
        return self._get_tools_for_context(ctx)

    def _call_ai_with_tools(self, messages: List[Dict], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Call AI provider with tool definitions (non-streaming).

        Subclasses (e.g. OpenRouterOrchestrator) must override this method.
        """
        raise NotImplementedError("Subclasses must override _call_ai_with_tools")

    async def _call_ai_with_tools_streaming(self, messages: List[Dict], ctx: Dict[str, Any]) -> AsyncGenerator[Dict[str, Any], None]:
        """Call AI provider with tool definitions (async streaming).

        Subclasses (e.g. OpenRouterOrchestrator) must override this method.
        """
        raise NotImplementedError("Subclasses must override _call_ai_with_tools_streaming")
        yield  # Make it an async generator  # noqa: unreachable

    def _execute_lite(self, messages: List[Dict], ctx: Dict[str, Any]) -> Dict[str, Any]:
        """Execute lite route (no tools). Subclasses must override."""
        raise NotImplementedError("Subclasses must override _execute_lite")

    async def _execute_lite_streaming(
        self, messages: List[Dict], ctx: Dict[str, Any]
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute lite route with streaming (no tools). Subclasses must override."""
        raise NotImplementedError("Subclasses must override _execute_lite_streaming")
        yield  # Make it an async generator  # noqa: unreachable

    async def _execute_with_tools_streaming(
        self,
        messages: List[Dict],
        ctx: Dict[str, Any],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute with tool calling and async streaming.

        Subclasses (e.g. OpenRouterOrchestrator) must override this method.
        """
        raise NotImplementedError("Subclasses must override _execute_with_tools_streaming")
        yield  # Make it an async generator  # noqa: unreachable

    def _execute_tool_calls(self, tool_calls: List[Dict], ctx: Dict[str, Any]) -> List[Dict]:
        """Execute the tool calls and return results."""
        # Ensure user_role is set - callers via handle_message always set this,
        # but direct callers may omit it. Fail closed to viewer-level permissions.
        ctx.setdefault("user_role", "viewer")
        ctx.setdefault("is_owner", False)
        results = []
        policy_decision = ctx.get("policy_decision")

        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("arguments") or {}

            logger.info(f"Executing tool: {name} with args: {args}")

            try:
                if self._is_tool_blocked_by_policy(name, policy_decision):
                    logger.info("[PolicyScope] blocked tool=%s for intent=%s", name, getattr(policy_decision, "intent", "unknown"))
                    results.append(
                        {
                            "name": name,
                            "result": {
                                "status": "blocked",
                                "message": f"Tool '{name}' blocked by policy for this user intent.",
                            },
                        }
                    )
                    continue

                args = self._normalize_tool_arguments(
                    tool_name=name,
                    args=args,
                    ctx=ctx,
                    policy_decision=policy_decision if isinstance(policy_decision, PolicyDecision) else None,
                )

                # Enforce paper limit for search_papers and batch_search_papers
                if name in ("search_papers", "batch_search_papers"):
                    max_papers = ctx.get("max_papers", 100)
                    papers_so_far = ctx.get("papers_requested", 0)

                    if name == "search_papers":
                        requested_count = args.get("limit", args.get("count", 1))
                    else:
                        # batch: sum of per-topic max_results (default 5 each)
                        requested_count = sum(
                            t.get("max_results", 5) for t in (args.get("topics") or [])[:5]
                        )

                    if papers_so_far >= max_papers:
                        logger.debug(f"Paper limit reached: {papers_so_far}/{max_papers}")
                        result = {
                            "status": "blocked",
                            "message": f"Paper limit reached ({max_papers}). No more searches.",
                        }
                        results.append({"name": name, "result": result})
                        continue

                    # Reduce count if it would exceed limit
                    remaining = max_papers - papers_so_far
                    if name == "search_papers" and requested_count > remaining:
                        args["count"] = remaining
                        args["limit"] = remaining
                        logger.debug(f"Reduced search count from {requested_count} to {remaining}")

                    # Track papers requested
                    ctx["papers_requested"] = papers_so_far + min(requested_count, remaining)

                if name in ("search_papers", "batch_search_papers"):
                    ctx.setdefault("_executed_search_args", []).append(
                        {
                            "tool": name,
                            "query": args.get("query"),
                            "count": args.get("count"),
                            "limit": args.get("limit"),
                            "open_access_only": args.get("open_access_only"),
                            "year_from": args.get("year_from"),
                            "year_to": args.get("year_to"),
                        }
                    )

                # Check cache for cacheable tools
                # NOTE: We no longer cache get_project_references since library can change frequently
                # and stale cache causes major issues (AI sees wrong count)
                channel = ctx.get("channel")
                cached_result = None
                if name in {"get_project_papers"} and channel:  # Removed get_project_references from cache
                    cached_result = self.get_cached_tool_result(channel, name, max_age_seconds=300)
                    if cached_result:
                        logger.info(f"Using cached result for {name}")
                        results.append({"name": name, "result": cached_result})
                        continue

                try:
                    result = self._tool_registry.execute(name, self, ctx, args)
                except KeyError:
                    result = {"error": f"Unknown tool: {name}"}

                # Cache the result for get_project_papers
                if name == "get_project_papers" and channel and result.get("count", 0) > 0:
                    self.cache_tool_result(channel, name, result)

                results.append({"name": name, "result": result})
                self._persist_last_effective_search_topic(ctx, name, args, result)

            except Exception as e:
                logger.exception(f"Error executing tool {name}")
                results.append({"name": name, "error": str(e)})

        return results

    def _enforce_finding_papers_stage_after_search(
        self,
        ctx: Dict[str, Any],
        tool_results: List[Dict[str, Any]],
    ) -> bool:
        """Deterministically set stage to finding_papers after successful search execution."""
        if not tool_results:
            return False
        channel = ctx.get("channel")
        if channel is None:
            return False

        search_succeeded = False
        for tr in tool_results:
            tool_name = tr.get("name")
            if tool_name not in ("search_papers", "batch_search_papers"):
                continue
            result = tr.get("result")
            if isinstance(result, dict) and result.get("status") == "success":
                search_succeeded = True
                break

        if not search_succeeded:
            return False

        try:
            memory = self._get_ai_memory(channel)
            research_state = memory.get("research_state", {})
            current_stage = research_state.get("stage", "exploring")
            if current_stage == "finding_papers":
                return True

            stage_history = research_state.get("stage_history", [])
            stage_history.append({
                "from": current_stage,
                "to": "finding_papers",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "reason": "search_tool_success",
            })

            research_state["stage_history"] = stage_history[-10:]
            research_state["stage"] = "finding_papers"
            research_state["stage_confidence"] = max(
                float(research_state.get("stage_confidence", 0.5)),
                0.95,
            )
            memory["research_state"] = research_state
            self._save_ai_memory(channel, memory)
            logger.info(
                "[StageTransition] %s",
                json.dumps(
                    {
                        "from": current_stage,
                        "to": "finding_papers",
                        "reason": "search_tool_success",
                    }
                ),
            )
            return True
        except Exception as exc:
            logger.warning("Failed to enforce finding_papers stage: %s", exc)
            return False

    def _record_quality_metrics(
        self,
        ctx: Dict[str, Any],
        policy_decision: PolicyDecision,
        tool_results: List[Dict[str, Any]],
        clarification_first_detected: bool,
        stage_transition_success: bool,
    ) -> None:
        """Record per-turn quality counters for policy and routing behavior."""
        try:
            direct_search_intent = policy_decision.intent == "direct_search"
            search_tool_called = any(
                tr.get("name") in ("search_papers", "batch_search_papers")
                for tr in tool_results
            )
            search_succeeded = any(
                tr.get("name") in ("search_papers", "batch_search_papers")
                and isinstance(tr.get("result"), dict)
                and tr.get("result", {}).get("status") == "success"
                for tr in tool_results
            )

            recency_requested = bool(
                policy_decision.search
                and (
                    policy_decision.search.year_from is not None
                    or policy_decision.search.year_to is not None
                )
            )
            executed_args = ctx.get("_executed_search_args") or []
            recency_filter_applied = any(
                args.get("year_from") is not None or args.get("year_to") is not None
                for args in executed_args
            )

            self._quality_metrics.record_turn(
                direct_search_intent=direct_search_intent,
                search_tool_called=search_tool_called,
                clarification_first_detected=clarification_first_detected,
                recency_requested=recency_requested,
                recency_filter_applied=recency_filter_applied,
                stage_transition_expected=search_succeeded,
                stage_transition_success=stage_transition_success,
            )
        except Exception as exc:
            logger.debug("Failed to record quality metrics: %s", exc)

    def _extract_actions(
        self,
        message: str,
        tool_results: List[Dict],
    ) -> List[Dict]:
        """Extract actions that should be sent to the frontend."""
        # Action types that are completed (already executed) - mark them for frontend display
        COMPLETED_ACTION_TYPES = {
            "paper_created",
            "paper_updated",
            "artifact_created",
            "search_results",  # Search already executed, results included
            "library_update",  # Library updates already applied
        }

        # Default summaries for action types
        ACTION_SUMMARIES = {
            "search_results": "View search results",
            "search_references": "Search for papers",
            "paper_created": "View created paper",
            "paper_updated": "View updated paper",
            "artifact_created": "Download artifact",
            "create_task": "Create task",
            "create_paper": "Create paper",
            "edit_paper": "Apply edit",
            "library_update": "Library updated",
        }

        actions = []

        for tr in tool_results:
            result = tr.get("result", {})
            if isinstance(result, dict) and result.get("action"):
                raw_action = result["action"]
                action_type = raw_action.get("type", "")

                # Transform to frontend format: action_type instead of type
                transformed_action = {
                    "action_type": action_type,
                    "summary": raw_action.get("summary") or ACTION_SUMMARIES.get(action_type, action_type),
                    "payload": raw_action.get("payload", {}),
                }

                # Mark completed actions so frontend can display them appropriately
                if action_type in COMPLETED_ACTION_TYPES:
                    transformed_action["completed"] = True

                actions.append(transformed_action)

        return actions
