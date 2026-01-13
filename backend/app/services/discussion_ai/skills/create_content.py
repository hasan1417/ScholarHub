"""
CreateContent Skill - Handles creating literature reviews, summaries, etc.

This skill manages a 3-turn conversation:
1. CLARIFYING: Ask user about theme, length, structure
2. CONFIRMING: Ask paper vs chat
3. EXECUTING: Generate the content

Each state has a focused prompt (no 100+ lines of instructions).
"""

from __future__ import annotations

from typing import List

from .base import BaseSkill, Intent, SkillContext, SkillResult, SkillState


class CreateContentSkill(BaseSkill):
    """
    Handles content creation requests (literature review, summary, etc.)

    State Machine:
        IDLE → CLARIFYING → CONFIRMING → EXECUTING → COMPLETE

    The state is tracked explicitly in code, not by hoping the LLM remembers.
    """

    name = "create_content"
    description = "Create literature reviews, summaries, and other content"
    handles_intents = [Intent.CREATE_CONTENT]

    # This skill needs search results to know what papers to use
    needs_search_results = True
    needs_conversation_history = False  # We track state explicitly
    needs_project_papers = False        # Don't show - it confuses the LLM

    # Focused prompts for each state (short and clear)
    CLARIFY_PROMPT = """You are helping create a {content_type}.
The user has these papers available:
{papers_list}

Ask 2-3 SHORT questions to understand what they want:
1. What theme/angle to focus on?
2. How long (brief 2 pages, or comprehensive 5+ pages)?
3. Structure preference (thematic, chronological, methodological)?

Keep your response under 100 words. Just ask the questions, nothing else."""

    CONFIRM_PROMPT = """The user wants a {content_type} with these specifications:
- Theme: {theme}
- Length: {length}
- Structure: {structure}
- Using papers: {papers_list}

Confirm the specifications briefly and ask:
"Create as paper or write in chat?"

Keep it under 50 words."""

    EXECUTE_PROMPT = """Write a {content_type} with these specifications:
- Theme: {theme}
- Length: {length}
- Structure: {structure}

Papers to use:
{papers_list}

Write the FULL content now. Use markdown formatting with headers.
Do NOT ask any questions. Just write the {content_type}."""

    def handle(self, ctx: SkillContext) -> SkillResult:
        """Handle based on current state."""

        if ctx.skill_state == SkillState.IDLE:
            return self._handle_new_request(ctx)
        elif ctx.skill_state == SkillState.CLARIFYING:
            return self._handle_clarification_response(ctx)
        elif ctx.skill_state == SkillState.CONFIRMING:
            return self._handle_confirmation_response(ctx)
        else:
            # Unknown state, reset
            return self._handle_new_request(ctx)

    def _handle_new_request(self, ctx: SkillContext) -> SkillResult:
        """User just asked to create something. Check if we have enough info or ask questions."""

        content_type = ctx.skill_data.get("content_type", "literature review")
        theme = ctx.skill_data.get("theme")
        length = ctx.skill_data.get("length")
        structure = ctx.skill_data.get("structure")
        output = ctx.skill_data.get("output")
        papers = ctx.recent_search_results or []

        # Check if all parameters are provided - smart multi-turn
        has_all_params = theme and length and structure and output

        if has_all_params:
            # All parameters provided - execute immediately
            return self._generate_content(
                content_type=content_type,
                theme=theme,
                length=length,
                structure=structure,
                output=output,
                papers=papers,
            )

        # Check if we have theme + length + structure but missing output
        if theme and length and structure:
            # Just need to ask about output format
            return SkillResult(
                message=f"Got it! I'll create a {length} {structure} {content_type} about {theme}. Create as paper or write in chat?",
                next_state=SkillState.CONFIRMING,
                state_data={
                    "content_type": content_type,
                    "theme": theme,
                    "length": length,
                    "structure": structure,
                    "papers": papers,
                },
            )

        # Missing some parameters - ask only for what's missing
        papers_list = self._format_papers(papers)
        missing = []
        if not theme:
            missing.append("theme/angle")
        if not length:
            missing.append("length (brief 2 pages or comprehensive 5+ pages)")
        if not structure:
            missing.append("structure (thematic, chronological, or methodological)")

        prompt = self.CLARIFY_PROMPT.format(
            content_type=content_type,
            papers_list=papers_list,
        )

        response = self._call_llm(
            system_prompt=prompt,
            user_message=ctx.user_message,
            reasoning_effort="low",
            max_tokens=300,
        )

        return SkillResult(
            message=response,
            next_state=SkillState.CLARIFYING,
            state_data={
                "content_type": content_type,
                "theme": theme,
                "length": length,
                "structure": structure,
                "papers": papers,
            },
        )

    def _generate_content(
        self,
        content_type: str,
        theme: str,
        length: str,
        structure: str,
        output: str,
        papers: list,
    ) -> SkillResult:
        """Generate the content and return result."""
        prompt = self.EXECUTE_PROMPT.format(
            content_type=content_type,
            theme=theme,
            length=length,
            structure=structure,
            papers_list=self._format_papers_detailed(papers),
        )

        response = self._call_llm(
            system_prompt=prompt,
            user_message=f"Generate the {content_type} now.",
            reasoning_effort="high",
            max_tokens=3000,
        )

        wants_paper = output == "paper"

        if wants_paper:
            return SkillResult(
                message="Creating the paper now.",
                next_state=SkillState.COMPLETE,
                actions=[{
                    "type": "create_paper",
                    "summary": f"Create {content_type}: {theme}",
                    "payload": {
                        "title": f"{content_type.title()}: {theme}",
                        "paper_type": "review" if "review" in content_type else "research",
                        "authoring_mode": "rich",
                        "abstract": f"A {length} {content_type} focusing on {theme}.",
                        "objectives": [theme],
                        "content": response,
                    }
                }],
            )
        else:
            return SkillResult(
                message=response,
                next_state=SkillState.COMPLETE,
            )

    def _handle_clarification_response(self, ctx: SkillContext) -> SkillResult:
        """User answered clarifying questions. Parse and ask paper vs chat."""

        # Parse user's answers
        parsed = self._parse_clarification(ctx.user_message)
        content_type = ctx.skill_data.get("content_type", "literature review")
        papers = ctx.skill_data.get("papers", [])

        prompt = self.CONFIRM_PROMPT.format(
            content_type=content_type,
            theme=parsed.get("theme", "as specified"),
            length=parsed.get("length", "2 pages"),
            structure=parsed.get("structure", "thematic"),
            papers_list=self._format_papers(papers),
        )

        response = self._call_llm(
            system_prompt=prompt,
            user_message=f"User specified: {ctx.user_message}",
            reasoning_effort="none",
            max_tokens=150,
        )

        return SkillResult(
            message=response,
            next_state=SkillState.CONFIRMING,
            state_data={
                **ctx.skill_data,
                "theme": parsed.get("theme"),
                "length": parsed.get("length"),
                "structure": parsed.get("structure"),
            },
        )

    def _handle_confirmation_response(self, ctx: SkillContext) -> SkillResult:
        """User said 'paper' or 'chat'. Generate content accordingly."""

        user_choice = ctx.user_message.lower().strip()
        wants_paper = any(x in user_choice for x in ["paper", "as paper", "create paper", "new paper"])

        content_type = ctx.skill_data.get("content_type", "literature review")
        theme = ctx.skill_data.get("theme", "general overview")
        length = ctx.skill_data.get("length", "2 pages")
        structure = ctx.skill_data.get("structure", "thematic")
        papers = ctx.skill_data.get("papers", [])

        prompt = self.EXECUTE_PROMPT.format(
            content_type=content_type,
            theme=theme,
            length=length,
            structure=structure,
            papers_list=self._format_papers_detailed(papers),
        )

        # Use higher reasoning effort for actual content generation
        response = self._call_llm(
            system_prompt=prompt,
            user_message=f"Generate the {content_type} now.",
            reasoning_effort="high",
            max_tokens=3000,
        )

        if wants_paper:
            # Return action to create paper
            return SkillResult(
                message="Creating the paper now.",
                next_state=SkillState.COMPLETE,
                actions=[{
                    "type": "create_paper",
                    "summary": f"Create {content_type}: {theme}",
                    "payload": {
                        "title": f"{content_type.title()}: {theme}",
                        "paper_type": "review" if "review" in content_type else "research",
                        "authoring_mode": "rich",
                        "abstract": f"A {length} {content_type} focusing on {theme}.",
                        "objectives": [theme],
                        "content": response,
                    }
                }],
            )
        else:
            # Write in chat
            return SkillResult(
                message=response,
                next_state=SkillState.COMPLETE,
            )

    def _format_papers(self, papers: List[dict] | None) -> str:
        """Format papers list for prompt (brief)."""
        if not papers:
            return "(no papers available)"

        lines = []
        for i, p in enumerate(papers[:10], 1):
            title = p.get("title", "Untitled")
            year = p.get("year", "")
            lines.append(f"{i}. {title} ({year})" if year else f"{i}. {title}")
        return "\n".join(lines)

    def _format_papers_detailed(self, papers: List[dict] | None) -> str:
        """Format papers with more detail for content generation."""
        if not papers:
            return "(no papers available)"

        lines = []
        for i, p in enumerate(papers[:10], 1):
            title = p.get("title", "Untitled")
            authors = p.get("authors", "")
            year = p.get("year", "")
            abstract = p.get("abstract", "")[:200] if p.get("abstract") else ""

            line = f"{i}. \"{title}\""
            if authors:
                line += f" by {authors}"
            if year:
                line += f" ({year})"
            if abstract:
                line += f"\n   Abstract: {abstract}..."
            lines.append(line)
        return "\n".join(lines)

    def _parse_clarification(self, message: str) -> dict:
        """Parse user's clarification answers."""
        result = {}
        msg_lower = message.lower()

        # Extract theme (usually the first thing mentioned or after "1.")
        if "1." in message:
            parts = message.split("2.")
            if parts:
                theme_part = parts[0].replace("1.", "").strip()
                result["theme"] = theme_part

        # Extract length
        if "2 page" in msg_lower or "brief" in msg_lower or "short" in msg_lower:
            result["length"] = "2 pages (brief)"
        elif "5 page" in msg_lower or "comprehensive" in msg_lower or "detailed" in msg_lower:
            result["length"] = "5+ pages (comprehensive)"
        else:
            result["length"] = "2 pages"

        # Extract structure
        if "thematic" in msg_lower or "theme" in msg_lower:
            result["structure"] = "thematic"
        elif "chronological" in msg_lower or "timeline" in msg_lower:
            result["structure"] = "chronological"
        elif "methodological" in msg_lower or "method" in msg_lower:
            result["structure"] = "methodological"
        else:
            result["structure"] = "thematic"

        # If no theme extracted, use the whole message
        if "theme" not in result:
            result["theme"] = message.strip()

        return result
