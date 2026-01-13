"""
Chat Skill - Handles general conversation, greetings, questions.

This is the fallback skill for messages that don't match other intents.
"""

from __future__ import annotations

from .base import BaseSkill, Intent, SkillContext, SkillResult, SkillState


class ChatSkill(BaseSkill):
    """
    Handles general conversation and questions.

    This is the fallback skill when no specific intent is detected.
    """

    name = "chat"
    description = "General conversation and questions"
    handles_intents = [Intent.CHAT, Intent.UNKNOWN]

    # May need context for answering questions
    needs_search_results = True
    needs_project_references = True

    CHAT_PROMPT = """You are a helpful research assistant for the project "{project_title}".
Keep responses brief and friendly. If the user asks about papers, use the context provided.

Available references:
{references}

Respond naturally to the user's message."""

    def handle(self, ctx: SkillContext) -> SkillResult:
        """Handle general chat/questions."""

        references = self._format_references(ctx)

        prompt = self.CHAT_PROMPT.format(
            project_title=ctx.project_title,
            references=references,
        )

        response = self._call_llm(
            system_prompt=prompt,
            user_message=ctx.user_message,
            reasoning_effort="none",
            max_tokens=500,
        )

        return SkillResult(
            message=response,
            next_state=SkillState.COMPLETE,
        )

    def _format_references(self, ctx: SkillContext) -> str:
        """Format available references for context."""
        lines = []

        if ctx.recent_search_results:
            for p in ctx.recent_search_results[:5]:
                lines.append(f"- {p.get('title', 'Untitled')} ({p.get('year', '')})")

        if ctx.project_references:
            for r in ctx.project_references[:5]:
                lines.append(f"- {r.get('title', 'Untitled')}")

        return "\n".join(lines) if lines else "(no references available)"
