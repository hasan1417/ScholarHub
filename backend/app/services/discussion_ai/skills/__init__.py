"""
Discussion AI Skills - Modular handlers for different user intents.

This is the new skill-based architecture that replaces the monolithic prompt approach.

Usage:
    from app.services.discussion_ai.skills import DiscussionOrchestrator

    orchestrator = DiscussionOrchestrator(ai_service)
    result = orchestrator.handle_message(project, channel, message)

To add a new skill:
    1. Create a new file in this directory (e.g., summarize.py)
    2. Create a class inheriting from BaseSkill
    3. Implement the handle() method
    4. Register it in SkillRegistry._register_default_skills()
"""

from .base import (
    BaseSkill,
    Intent,
    SkillContext,
    SkillResult,
    SkillState,
    ClassifiedIntent,
)
from .router import IntentRouter
from .orchestrator import DiscussionOrchestrator, SkillRegistry, SessionState

# Individual skills (for direct access if needed)
from .search import SearchSkill
from .create_content import CreateContentSkill
from .explain import ExplainSkill
from .chat import ChatSkill

__all__ = [
    # Main entry point
    "DiscussionOrchestrator",

    # Base classes (for creating new skills)
    "BaseSkill",
    "Intent",
    "SkillContext",
    "SkillResult",
    "SkillState",
    "ClassifiedIntent",

    # Components
    "IntentRouter",
    "SkillRegistry",
    "SessionState",

    # Built-in skills
    "SearchSkill",
    "CreateContentSkill",
    "ExplainSkill",
    "ChatSkill",
]
