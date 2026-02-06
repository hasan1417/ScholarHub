"""
Tool-Based Discussion AI Orchestrator

Uses OpenAI function calling to let the AI decide what context it needs.
Instead of hardcoding what data each skill uses, the AI calls tools on-demand.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional, TYPE_CHECKING

from app.services.discussion_ai.tools import build_tool_registry
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

# System prompt with adaptive workflow based on request clarity
BASE_SYSTEM_PROMPT = r"""You are a research assistant helping with academic papers.

## GOLDEN RULE: USE WHAT YOU HAVE

Use existing context before searching for new things. If you just searched, discussed, or analyzed papers, those ARE the context. Only search when the user explicitly asks for NEW papers or there's nothing relevant in context.

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

**Query tips:** Use academic terminology, keep queries to 2-5 key terms. Include year only when user specifically mentions a timeframe.

## GUIDELINES

1. Be dynamic and contextual — never ask more than ONE clarifying question
2. Never invent papers from training data — only use search results
3. For general knowledge questions, answer first, then offer to search
4. Output markdown naturally (not in code blocks)
5. For long content, offer to create as a paper instead of dumping in chat
6. Never show UUIDs — use titles and relevant info
7. Always confirm what you created by name
8. When user confirms an action ("yes", "do it", "all") → CALL the tool immediately, don't just respond with text

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

    def __init__(self, ai_service: "AIService", db: "Session"):
        self.ai_service = ai_service
        self.db = db
        self._tool_registry = DISCUSSION_TOOL_REGISTRY

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
        try:
            # Build request context (thread-safe - local variable)
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

            # Build messages for LLM
            messages = self._build_messages(project, channel, message, recent_search_results, conversation_history, ctx=ctx)

            # Execute with tools
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
        try:
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
        logger.debug(f"[Permission] User role: {user_role}, is_owner: {is_owner}")

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
        memory_context = self._build_memory_context(channel)

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

        messages = [{"role": "system", "content": system_prompt}]

        # Add role-based permission notice for viewers
        # Viewers have NO tools - they can only chat about existing content
        user_role = ctx.get("user_role") if ctx else None
        if user_role == "viewer":
            viewer_notice = """
CRITICAL - VIEWER ACCESS ONLY:
You are assisting a VIEWER (read-only member) of this project.

As a viewer, you have NO tools available. You CANNOT:
- Search for papers
- Add papers to the library
- Create or edit papers/documents
- Modify project settings
- Take ANY actions

You CAN ONLY:
- Answer questions about the project based on the context provided above
- Discuss papers that are already in the library (shown in context)
- Have a general conversation

If the user asks you to search, add, create, or modify ANYTHING, respond with:
"As a viewer, I can only discuss existing content in this project. To search for papers, add to the library, or create content, you'll need editor or admin access. Please contact the project owner to upgrade your role."

DO NOT pretend to take actions. DO NOT say "I'll search for..." or "Let me add...". Be direct about your limitations."""
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
        try:
            max_iterations = 8
            iteration = 0
            all_tool_results = []
            response = {"content": "", "tool_calls": []}

            while iteration < max_iterations:
                iteration += 1
                logger.info(f"Tool orchestrator iteration {iteration}")

                response = self._call_ai_with_tools(messages, ctx)
                tool_calls = response.get("tool_calls", [])

                if not tool_calls:
                    break

                # Execute tool calls
                tool_results = self._execute_tool_calls(tool_calls, ctx)
                all_tool_results.extend(tool_results)

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
            actions = self._extract_actions(final_message, all_tool_results)

            # Update AI memory after successful response (async in background)
            contradiction_warning = None
            try:
                contradiction_warning = self.update_memory_after_exchange(
                    ctx["channel"],
                    ctx["user_message"],
                    final_message,
                    ctx.get("conversation_history", []),
                )
                if contradiction_warning:
                    logger.info(f"Contradiction detected: {contradiction_warning}")
            except Exception as mem_err:
                logger.error(f"Failed to update AI memory: {mem_err}")

            return {
                "message": final_message,
                "actions": actions,
                "citations": [],
                "model_used": self.model,
                "reasoning_used": ctx.get("reasoning_mode", False),
                "tools_called": [t["name"] for t in all_tool_results] if all_tool_results else [],
                "conversation_state": {},
                "memory_warning": contradiction_warning,  # Include contradiction warning
            }

        except Exception as e:
            logger.exception(f"Error in _execute_with_tools: {e}")
            return self._error_response(str(e))

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

    def _get_tools_for_user(self, ctx: Dict[str, Any]) -> List[Dict]:
        """Get tools filtered by user's role.

        This ensures the LLM only sees tools the user is allowed to use.
        - Viewers: NO tools (read-only, can only chat about existing content)
        - Editors: Read + write tools
        - Admins: All tools including admin tools
        """
        user_role = ctx.get("user_role", "viewer")
        is_owner = ctx.get("is_owner", False)

        # Viewers get NO tools - they can only chat, not take actions
        if user_role == "viewer":
            logger.debug("[Permission] Viewer role - NO tools available")
            return []

        tools = DISCUSSION_TOOL_REGISTRY.get_schema_list_for_role(user_role, is_owner)
        logger.debug(f"[Permission] Role '{user_role}': {len(tools)} tools available")
        return tools

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
        # but direct callers (e.g. tests) may omit it
        ctx.setdefault("user_role", "admin")
        ctx.setdefault("is_owner", True)
        results = []

        for tc in tool_calls:
            name = tc["name"]
            args = tc.get("arguments") or {}

            logger.info(f"Executing tool: {name} with args: {args}")

            try:
                # Enforce paper limit for search_papers
                if name == "search_papers":
                    max_papers = ctx.get("max_papers", 100)
                    papers_so_far = ctx.get("papers_requested", 0)
                    requested_count = args.get("count", 1)

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
                    if requested_count > remaining:
                        args["count"] = remaining
                        logger.debug(f"Reduced search count from {requested_count} to {remaining}")

                    # Track papers requested
                    ctx["papers_requested"] = papers_so_far + args.get("count", 1)

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

            except Exception as e:
                logger.exception(f"Error executing tool {name}")
                results.append({"name": name, "error": str(e)})

        return results

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
            "batch_search_references": "Search multiple topics",
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
