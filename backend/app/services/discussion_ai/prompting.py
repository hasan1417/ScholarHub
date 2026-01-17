from __future__ import annotations

from textwrap import dedent
from typing import Iterable, List, Sequence

from app.models import ProjectDiscussionResourceType
from app.services.discussion_ai.types import ChannelContext, RetrievalSnippet


_SYSTEM_PROMPT = dedent(
    """
    ############################################################
    # MANDATORY RULE - YOU MUST FOLLOW THIS BEFORE ANYTHING ELSE
    ############################################################

    When user asks to CREATE, WRITE, GENERATE, or MAKE any content:

    1. DO NOT create the content yet
    2. Ask 2-3 clarifying questions (ONLY ONE ROUND - do NOT ask more questions after user answers)
    3. After user answers → immediately ask: "Create as paper or write in chat?"
    4. If user says "paper" → include create_paper action
    5. If user says "chat" → write the full content directly in your response

    IMPORTANT:
    - Only ONE round of questions. After user answers, go directly to "paper or chat?"
    - Do NOT ask follow-up clarifying questions after user already answered
    - When user says "above references" or "these papers", use the "Recently discovered papers" from the context
    - Remember: the recently discovered papers ARE the references the user wants to use

    ############################################################

    You are ScholarHub's project discussion assistant. Help researchers by answering
    questions using only the information provided. If the context does not contain
    enough details, ask the user to clarify or suggest linking additional resources.

    RESPONSE FORMAT:
    - NEVER show UUIDs or identifiers like [reference:abc-123] in your response
    - Just refer to resources by their title/name naturally (e.g., "Agentic AI in Enterprise (2025)")
    - The UI will automatically link citations - you don't need to include IDs
    - Keep responses concise and natural
    - NEVER comment on system limits, constraints, or what you "can" or "cannot" do
    - Just fulfill the user's request directly without meta-commentary

    CITATION RULES:
    - Only cite sources when you actually use specific information FROM that source
    - Do NOT cite a source just because it exists in the context
    - Do NOT cite meeting transcripts unless you quote or reference specific content from them
    - If no sources are relevant to your answer, don't include any citations
    - For internal tracking only, use format [resource:<id>] but this will be hidden from users

    Never fabricate data. Do not invent URLs or external links.

    SUGGESTED ACTIONS:
    After your response text, you MUST add a JSON array between <actions> and </actions> tags.
    If you say "I'll create..." or "I'll search...", you MUST include the corresponding action.

    Supported action types:

    1. **create_task** - Create a specific, actionable task
       {"type": "create_task", "summary": "Short label", "payload": {"title": "...", "description": "..."}}
       ONLY suggest tasks that are:
       - Specific and actionable (e.g., "Review reference X for methodology section")
       - NOT vague organizational suggestions (e.g., "Organize by theme" is NOT a valid task)
       - Related to concrete work the user can do

    2. **create_paper** - Create a new research paper or literature review
       {"type": "create_paper", "summary": "Create [type] paper: [title]", "payload": {"title": "Paper Title", "paper_type": "research|review|case_study", "authoring_mode": "rich", "abstract": "Brief abstract", "objectives": [], "content": "# Title\n\nFull paper content in markdown..."}}
       - CRITICAL: NEVER include this action on first request
       - ONLY use after: (1) you asked clarifying questions, (2) user answered, (3) user said "create as paper"
       - For literature reviews, use paper_type: "review"
       - Use authoring_mode: "rich" (markdown) unless user specifically requests LaTeX
       - Include actual written content in the "content" field (markdown format)

    3. **edit_paper** - Suggest an edit to an existing paper
       {"type": "edit_paper", "summary": "Brief description", "payload": {"paper_id": "<uuid>", "original": "Exact text to find", "proposed": "Replacement text", "description": "Why this change"}}

    4. **search_references** - Search for academic papers to add as project references
       {"type": "search_references", "summary": "Search for N papers about topic", "payload": {"query": "<user's exact words>", "max_results": <number>, "open_access_only": false}}
       - ALWAYS honor the user's requested count in max_results (supports 1-20)
       - Set open_access_only: true when user wants PDFs or "free" papers

       *** CRITICAL QUERY RULE ***
       Copy the user's EXACT topic into the query field. Do NOT "help" by adding terms.

       User says: "search for papers about metaheuristics"
       CORRECT query: "metaheuristics"
       WRONG query: "metaheuristics survey 2023 2024" ← causes IRRELEVANT results!

       The search API handles relevance ranking. Your expanded terms HURT results.

    Emit an empty array [] if no concrete action is appropriate. Most informational responses
    should NOT have suggested actions - only suggest actions when they add real value.
    Do not mention the tags in the natural language response.

    EXAMPLE - Search for references (note: query is ONLY the topic, nothing else):
    User: "find 5 papers about metaheuristics"
    Response: "I'll search for 5 papers about metaheuristics."
    <actions>[{"type": "search_references", "summary": "Search for 5 papers about metaheuristics", "payload": {"query": "metaheuristics", "max_results": 5, "open_access_only": false}}]</actions>
    WRONG query: "metaheuristics survey 2023 2024 optimization" (too many terms!)
    CORRECT query: "metaheuristics" (just the topic)

    EXAMPLE - Exactly 3 turns for content creation (NO MORE):

    Turn 1 - User requests creation:
    User: "Create a literature review using the above 5 references"
    Response: "I'd be happy to help! A few questions:
    1. What theme should tie these papers together?
    2. How long - brief (2 pages) or comprehensive (5+ pages)?
    3. Structure preference (thematic, chronological, methodological)?"
    <actions>[]</actions>

    Turn 2 - User answers → YOU MUST ASK "paper or chat?" (NO more clarifying questions!):
    User: "methodology comparison, 2 pages, thematic"
    Response: "Got it - 2-page thematic review comparing methodologies across the 5 papers. Create as paper or write in chat?"
    <actions>[]</actions>

    Turn 3a - User says "paper":
    Response: "Creating the literature review now."
    <actions>[{"type": "create_paper", ...}]</actions>

    Turn 3b - User says "chat":
    Response: "# Literature Review: Methodology Comparison

    ## Introduction
    This review examines methodology across five key papers...
    [WRITE THE FULL 2-PAGE CONTENT HERE]"
    <actions>[]</actions>

    WRONG - Do NOT do this:
    - Asking more clarifying questions after user already answered (Turn 2 must be "paper or chat?")
    - Forgetting which references the user mentioned (use "Recently discovered papers" from context)
    - Saying "which references?" when user said "above 5 references" (they mean the recently discovered ones)
    """
).strip()


class PromptComposer:
    """Build chat prompts for the discussion assistant."""

    def __init__(self, system_prompt: str = _SYSTEM_PROMPT) -> None:
        self.system_prompt = system_prompt

    def build_messages(
        self,
        user_question: str,
        context: ChannelContext,
        snippets: Sequence[RetrievalSnippet],
    ) -> List[dict]:
        """Compose OpenAI-compatible message payload."""

        resource_section = self._format_resources(context)
        snippet_section = self._format_snippets(snippets)
        objectives_section = self._format_project_objectives(context)
        scope_section = self._format_scope(context)
        search_results_section = self._format_recent_search_results(context)

        # Check if user is giving a short confirmation answer
        q_lower = user_question.strip().lower()
        is_chat_confirmation = q_lower in ("chat", "chat please", "in chat", "write in chat", "in the chat")

        # If user says "chat", add explicit instruction to write content
        question_text = user_question.strip()
        if is_chat_confirmation:
            question_text = (
                f"{user_question.strip()}\n\n"
                "[SYSTEM: User confirmed 'chat'. You MUST now write the full content directly in your response. "
                "Do NOT ask any more questions. Do NOT ask about other papers. "
                "Write the literature review/content NOW using the recently discovered papers listed above.]"
            )

        # Simplified context for short answers to avoid confusion
        if is_chat_confirmation or len(user_question.split()) <= 5:
            # Don't include paper contents for editing - it confuses the AI
            user_payload = dedent(
                f"""
                Project: {context.project_title}
                {search_results_section}
                Question: {question_text}
                """
            ).strip()
        else:
            # Full context for complex questions
            message_history = self._format_messages(context)
            paper_section = self._format_paper_objectives(context)
            paper_contents_section = self._format_paper_contents(context)

            user_payload = dedent(
                f"""
                Project: {context.project_title}
                Channel: {context.channel_name}
                Channel summary: {context.summary or 'n/a'}
                Context scope: {scope_section}

                Project objectives:
                {objectives_section}

                Papers aligned to objectives:
                {paper_section}

                Paper contents for editing:
                {paper_contents_section}

                Recent discussion snippets:
                {message_history}

                Retrieved knowledge snippets:
                {snippet_section}
                {search_results_section}
                Question: {question_text}
                """
            ).strip()

        return [
            {"role": "system", "content": self.system_prompt},
            {"role": "assistant", "content": resource_section},
            {"role": "user", "content": user_payload},
        ]

    def _format_resources(self, context: ChannelContext) -> str:
        if not context.resources:
            return "Project resources: none available."

        # Group resources by type for clarity
        papers = [r for r in context.resources if r.resource_type == ProjectDiscussionResourceType.PAPER]
        references = [r for r in context.resources if r.resource_type == ProjectDiscussionResourceType.REFERENCE]
        meetings = [r for r in context.resources if r.resource_type == ProjectDiscussionResourceType.MEETING]

        lines: List[str] = ["Project resources:"]

        # Papers being written in the project
        lines.append(f"\nPapers (research papers being written by the team): {len(papers)} total")
        if papers:
            for resource in papers:
                meta = f" ({', '.join(resource.metadata)})" if resource.metadata else ""
                lines.append(f"  - [{resource.resource_type.value}:{resource.id}] {resource.title}{meta}")
        else:
            lines.append("  - (no papers yet)")

        # References in project library
        lines.append(f"\nReferences (academic papers in project library): {len(references)} total")
        if references:
            for resource in references:
                meta = f" ({', '.join(resource.metadata)})" if resource.metadata else ""
                lines.append(f"  - [{resource.resource_type.value}:{resource.id}] {resource.title}{meta}")
        else:
            lines.append("  - (no references in library)")

        # Meeting transcripts
        if meetings:
            lines.append(f"\nMeeting transcripts: {len(meetings)} total")
            for resource in meetings:
                meta = f" ({', '.join(resource.metadata)})" if resource.metadata else ""
                lines.append(f"  - [{resource.resource_type.value}:{resource.id}] {resource.title}{meta}")
                if resource.summary:
                    summary_preview = resource.summary.strip()
                    if len(summary_preview) > 320:
                        summary_preview = summary_preview[:317].rstrip() + "…"
                    lines.append(f"    Transcript: {summary_preview}")

        return "\n".join(lines)

    def _format_snippets(self, snippets: Sequence[RetrievalSnippet]) -> str:
        if not snippets:
            return "  • none"
        lines: List[str] = []
        for snippet in snippets:
            prefix = f"[{snippet.origin}:{snippet.origin_id}]"
            lines.append(f"  • {prefix} {snippet.content.strip()}")
        return "\n".join(lines)

    def _format_messages(self, context: ChannelContext) -> str:
        if not context.messages:
            return "  • none"
        lines: List[str] = []
        for message in context.messages[-10:]:  # the assembler already applied windowing
            label = f"[{message.author_name}]"
            lines.append(f"  • {label} {message.content.strip()}")
        return "\n".join(lines)

    def _format_project_objectives(self, context: ChannelContext) -> str:
        if not context.project_objectives:
            return "  • none"
        return "\n".join(f"  • {item}" for item in context.project_objectives)

    def _format_paper_objectives(self, context: ChannelContext) -> str:
        if not context.paper_objectives:
            return "  • none"
        lines: List[str] = []
        for digest in context.paper_objectives:
            objectives = ", ".join(digest.objectives)
            lines.append(f"  • {digest.title}: {objectives}")
        return "\n".join(lines)

    def _format_scope(self, context: ChannelContext) -> str:
        if not context.resource_scope:
            return "transcripts, papers, references"
        mapping = {
            "meeting": "transcripts",
            "paper": "papers",
            "reference": "references",
        }
        labels = []
        for value in context.resource_scope:
            label = mapping.get(value.value)
            if label:
                labels.append(label)
        return ", ".join(labels) if labels else "transcripts, papers, references"

    def _format_paper_contents(self, context: ChannelContext) -> str:
        """Format paper content previews for AI editing suggestions."""
        if not context.resources:
            return "  • none (no papers in project)"

        lines: List[str] = []
        for resource in context.resources:
            if resource.resource_type != ProjectDiscussionResourceType.PAPER:
                continue
            if not resource.content_preview:
                lines.append(f"  • [{resource.id}] {resource.title} - (no content yet)")
                continue

            mode = resource.authoring_mode or 'rich'
            lines.append(f"  • [{resource.id}] {resource.title} (mode: {mode})")
            # Include content preview (truncated for prompt efficiency)
            preview = resource.content_preview
            if len(preview) > 1500:
                preview = preview[:1500] + "...[truncated]"
            lines.append(f"    Content:\n    {preview}")

        if not lines:
            return "  • none (no papers in project)"
        return "\n".join(lines)

    def _format_recent_search_results(self, context: ChannelContext) -> str:
        """Format recent search results shown to user (for conversational context)."""
        if not context.recent_search_results:
            return ""

        lines: List[str] = ["\nRecently discovered papers (shown above in UI):"]
        for idx, paper in enumerate(context.recent_search_results, 1):
            author_info = f" by {paper.authors}" if paper.authors else ""
            year_info = f" ({paper.year})" if paper.year else ""
            source_info = f" [{paper.source}]" if paper.source else ""
            lines.append(f"  {idx}. {paper.title}{author_info}{year_info}{source_info}")

        return "\n".join(lines)
