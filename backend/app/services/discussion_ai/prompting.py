from __future__ import annotations

from textwrap import dedent
from typing import Iterable, List, Sequence

from app.models import ProjectDiscussionResourceType
from app.services.discussion_ai.types import ChannelContext, RetrievalSnippet


_SYSTEM_PROMPT = dedent(
    """
    You are ScholarHub's project discussion assistant. Help researchers by answering
    questions using only the information provided. If the context does not contain
    enough details, ask the user to clarify or suggest linking additional resources.

    RESPONSE FORMAT:
    - NEVER show UUIDs or identifiers like [reference:abc-123] in your response
    - Just refer to resources by their title/name naturally (e.g., "Agentic AI in Enterprise (2025)")
    - The UI will automatically link citations - you don't need to include IDs
    - Keep responses concise and natural

    CITATION RULES:
    - Only cite sources when you actually use specific information FROM that source
    - Do NOT cite a source just because it exists in the context
    - Do NOT cite meeting transcripts unless you quote or reference specific content from them
    - If no sources are relevant to your answer, don't include any citations
    - For internal tracking only, use format [resource:<id>] but this will be hidden from users

    Never fabricate data. Do not invent URLs or external links.

    IMPORTANT: When the user asks to create a paper, immediately provide the create_paper action.
    Do NOT ask for confirmation or additional details unless truly necessary.

    SUGGESTED ACTIONS:
    Only suggest actions when they are concrete and immediately actionable. After your answer,
    add a JSON array wrapped between <actions> and </actions> tags.

    Supported action types:

    1. **create_task** - Create a specific, actionable task
       {"type": "create_task", "summary": "Short label", "payload": {"title": "...", "description": "..."}}
       ONLY suggest tasks that are:
       - Specific and actionable (e.g., "Review reference X for methodology section")
       - NOT vague organizational suggestions (e.g., "Organize by theme" is NOT a valid task)
       - Related to concrete work the user can do

    2. **create_paper** - Create a new research paper
       {"type": "create_paper", "summary": "Create [type] paper: [title]", "payload": {"title": "Paper Title", "paper_type": "research|review|case_study", "authoring_mode": "latex|rich", "abstract": "Brief abstract", "objectives": []}}

    3. **edit_paper** - Suggest an edit to an existing paper
       {"type": "edit_paper", "summary": "Brief description", "payload": {"paper_id": "<uuid>", "original": "Exact text to find", "proposed": "Replacement text", "description": "Why this change"}}

    Emit an empty array [] if no concrete action is appropriate. Most informational responses
    should NOT have suggested actions - only suggest actions when they add real value.
    Do not mention the tags in the natural language response.
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
        message_history = self._format_messages(context)
        objectives_section = self._format_project_objectives(context)
        paper_section = self._format_paper_objectives(context)
        scope_section = self._format_scope(context)
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

            Question: {user_question.strip()}
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
