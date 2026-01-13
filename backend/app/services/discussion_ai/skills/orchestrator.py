"""
Discussion AI Orchestrator - Coordinates skills, manages state, handles actions.

This is the main entry point for the skill-based architecture.
It replaces the monolithic prompt approach with a modular system.
"""

from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, Dict, List, Optional, TYPE_CHECKING
from uuid import UUID

from .base import BaseSkill, Intent, SkillContext, SkillResult, SkillState, ClassifiedIntent
from .router import IntentRouter
from .search import SearchSkill
from .create_content import CreateContentSkill
from .chat import ChatSkill
from .explain import ExplainSkill

if TYPE_CHECKING:
    from app.services.ai_service import AIService
    from app.models import Project, ProjectDiscussionChannel

logger = logging.getLogger(__name__)


class SkillRegistry:
    """Registry of available skills."""

    def __init__(self, ai_service: "AIService"):
        self.ai_service = ai_service
        self._skills: Dict[str, BaseSkill] = {}
        self._intent_map: Dict[Intent, BaseSkill] = {}
        self._register_default_skills()

    def _register_default_skills(self):
        """Register built-in skills."""
        self.register(SearchSkill(self.ai_service))
        self.register(CreateContentSkill(self.ai_service))
        self.register(ExplainSkill(self.ai_service))
        self.register(ChatSkill(self.ai_service))

    def register(self, skill: BaseSkill):
        """Register a skill."""
        self._skills[skill.name] = skill
        for intent in skill.handles_intents:
            self._intent_map[intent] = skill
        logger.info(f"Registered skill: {skill.name}")

    def get_by_name(self, name: str) -> Optional[BaseSkill]:
        """Get skill by name."""
        return self._skills.get(name)

    def get_by_intent(self, intent: Intent) -> Optional[BaseSkill]:
        """Get skill that handles an intent."""
        return self._intent_map.get(intent)

    def list_skills(self) -> List[str]:
        """List all registered skill names."""
        return list(self._skills.keys())


class SessionState:
    """
    Per-session state storage.

    In production, this would be stored in Redis or database.
    For now, it's in-memory (resets on server restart).
    """

    def __init__(self):
        self._sessions: Dict[str, Dict[str, Any]] = {}

    def _key(self, channel_id: UUID) -> str:
        return str(channel_id)

    def get(self, channel_id: UUID) -> Dict[str, Any]:
        """Get session state for a channel."""
        key = self._key(channel_id)
        if key not in self._sessions:
            self._sessions[key] = {
                "current_skill": None,
                "skill_state": SkillState.IDLE.value,
                "skill_data": {},
            }
        return self._sessions[key]

    def set(self, channel_id: UUID, state: Dict[str, Any]):
        """Set session state for a channel."""
        self._sessions[self._key(channel_id)] = state

    def clear(self, channel_id: UUID):
        """Clear session state."""
        key = self._key(channel_id)
        if key in self._sessions:
            del self._sessions[key]


class DiscussionOrchestrator:
    """
    Main orchestrator for the Discussion AI.

    This coordinates:
    1. Intent classification (what does the user want?)
    2. Skill routing (which skill handles this?)
    3. State management (where are we in the conversation?)
    4. Context assembly (what info does the skill need?)
    5. Response handling (actions, citations, etc.)
    """

    def __init__(self, ai_service: "AIService"):
        self.ai_service = ai_service
        self.router = IntentRouter(ai_service)
        self.registry = SkillRegistry(ai_service)
        self.sessions = SessionState()

    def handle_message(
        self,
        project: "Project",
        channel: "ProjectDiscussionChannel",
        message: str,
        *,
        recent_search_results: Optional[List[Dict]] = None,
        reasoning_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Handle a user message.

        Returns a dict with:
        - message: str - Response text
        - actions: List[Dict] - Actions to execute
        - citations: List[Dict] - Citations to show
        - model_used: str - Model used
        - reasoning_used: bool - Whether reasoning was enabled
        """

        # 1. Get session state
        session = self.sessions.get(channel.id)
        current_skill = session.get("current_skill")
        skill_state = SkillState(session.get("skill_state", "idle"))
        skill_data = session.get("skill_data", {})

        # 2. Classify intent (or detect continuation)
        intent_result = self.router.classify(message, current_skill, skill_state)
        logger.info(f"Classified intent: {intent_result.intent.value} (confidence: {intent_result.confidence})")

        # 3. Determine which skill to use
        if intent_result.intent == Intent.CONTINUATION and current_skill:
            # Continue with current skill
            skill = self.registry.get_by_name(current_skill)
        else:
            # Route to appropriate skill
            skill = self.registry.get_by_intent(intent_result.intent)
            skill_state = SkillState.IDLE
            skill_data = intent_result.params

        if not skill:
            # Fallback to chat
            skill = self.registry.get_by_name("chat")

        logger.info(f"Using skill: {skill.name}, state: {skill_state.value}")

        # 4. Build context for skill
        ctx = SkillContext(
            project_id=project.id,
            project_title=project.title,
            channel_id=channel.id,
            user_message=message,
            current_skill=skill.name,
            skill_state=skill_state,
            skill_data=skill_data,
            recent_search_results=self._convert_search_results(recent_search_results),
        )

        # 5. Execute skill
        result = skill.handle(ctx)
        logger.info(f"Skill result: state={result.next_state.value}, actions={len(result.actions)}")

        # 6. Update session state
        if result.next_state == SkillState.COMPLETE:
            # Clear session - conversation done
            self.sessions.clear(channel.id)
        else:
            # Persist state for next turn
            self.sessions.set(channel.id, {
                "current_skill": skill.name,
                "skill_state": result.next_state.value,
                "skill_data": result.state_data,
            })

        # 7. Return response
        return {
            "message": result.message,
            "actions": result.actions,
            "citations": result.citations,
            "model_used": skill.model,
            "reasoning_used": reasoning_mode,
        }

    def _convert_search_results(self, results: Optional[List]) -> Optional[List[Dict]]:
        """Convert search results to dict format for skills."""
        if not results:
            return None

        converted = []
        for r in results:
            if hasattr(r, "__dict__"):
                # It's a dataclass or object
                converted.append({
                    "title": getattr(r, "title", ""),
                    "authors": getattr(r, "authors", ""),
                    "year": getattr(r, "year", None),
                    "source": getattr(r, "source", ""),
                    "abstract": getattr(r, "abstract", ""),
                })
            elif isinstance(r, dict):
                converted.append(r)
        return converted
