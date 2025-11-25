from __future__ import annotations

from textwrap import dedent
from typing import Iterable, List, Sequence

from app.services.discussion_ai.types import ChannelContext, RetrievalSnippet


_SYSTEM_PROMPT = dedent(
    """
    You are ScholarHub's project discussion assistant. Help researchers by answering
    questions using only the information provided. If the context does not contain
    enough details, ask the user to clarify or suggest linking additional resources.
    Always cite the source identifiers provided in the context snippets using the
    format [resource:<id>] or [message:<id>] where <id> is the UUID supplied.
    Never fabricate data and keep responses concise so the user receives an answer quickly.

    Do not invent URLs or external links. Refer to resources only by the names
    and identifiers given in the context. Do not include a separate "Sources" or
    reference list inside the natural language reply—the UI will surface citations
    automatically—so focus on the answer itself.

    When referencing meeting transcripts, clearly label them (e.g., "Transcript:")
    so the content stands out from the rest of the answer.

    When appropriate, propose follow-up actions (e.g., create a task). After your
    answer, add a JSON array wrapped between <actions> and </actions> tags. The JSON
    should follow this schema:

    <actions>
    [
      {
        "type": "create_task",
        "summary": "Short human-readable label",
        "payload": { "title": "...", "description": "...", "message_id": "..." }
      }
    ]
    </actions>

    Emit an empty array if no action is required. Do not mention the tags in the
    natural language response.
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
            return "Channel resources: none linked."
        lines: List[str] = ["Channel resources:"]
        for resource in context.resources:
            meta = f" ({', '.join(resource.metadata)})" if resource.metadata else ""
            lines.append(
                f"- [{resource.resource_type.value}:{resource.id}] {resource.title}{meta}"
            )
            if resource.summary:
                summary_preview = resource.summary.strip()
                if len(summary_preview) > 320:
                    summary_preview = summary_preview[:317].rstrip() + "…"
                lines.append(f"  Transcript: {summary_preview}")
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
