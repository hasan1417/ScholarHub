"""
Search Skill - Handles searching for papers/references.

This is a simple skill with no multi-turn flow.
It immediately returns a search action.
"""

from __future__ import annotations

from .base import BaseSkill, Intent, SkillContext, SkillResult, SkillState


class SearchSkill(BaseSkill):
    """
    Handles search requests.

    This is a simple skill - no multi-turn flow needed.
    Just parse the query and return a search action.
    """

    name = "search"
    description = "Search for papers and references"
    handles_intents = [Intent.SEARCH]

    # Minimal context needed
    needs_search_results = False
    needs_conversation_history = False
    needs_project_papers = False
    needs_project_references = False

    def handle(self, ctx: SkillContext) -> SkillResult:
        """Handle search request - return search action immediately."""

        # Get query and count from parsed intent (or extract from message)
        query = ctx.skill_data.get("query", ctx.user_message)
        count = ctx.skill_data.get("count", 5)

        return SkillResult(
            message=f"I'll search for {count} papers about {query}.",
            next_state=SkillState.COMPLETE,
            actions=[{
                "type": "search_references",
                "summary": f"Search for {count} papers about {query}",
                "payload": {
                    "query": query,
                    "max_results": count,
                    "open_access_only": False,
                }
            }],
        )
