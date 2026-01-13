"""
Base classes for the Skill-Based Discussion AI Architecture.

This follows the 2025-2026 best practices for modular AI agents:
- Dispatcher/Router Pattern for intent classification
- Skills as Finite State Machines for multi-turn flows
- Minimal context per skill to avoid confusion

References:
- LangGraph: Graph-based state machines for agents
- DSPy: Declarative modular AI systems
- Google ADK: Multi-agent patterns
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from uuid import UUID


class SkillState(str, Enum):
    """
    States a skill can be in during a multi-turn conversation.
    Each skill manages its own state machine.
    """
    IDLE = "idle"                  # Ready for new request
    CLARIFYING = "clarifying"      # Asking user for more info
    CONFIRMING = "confirming"      # Asking user to confirm (e.g., paper vs chat)
    EXECUTING = "executing"        # Generating output
    COMPLETE = "complete"          # Done, return to IDLE


class Intent(str, Enum):
    """
    Recognized user intents.
    Add new intents here when adding new skills.
    """
    SEARCH = "search"                    # "find papers about X", "search for references"
    CREATE_CONTENT = "create_content"    # "create literature review", "write summary"
    EDIT_PAPER = "edit_paper"            # "edit my paper", "fix the introduction"
    EXPLAIN = "explain"                  # "what does this paper say about X"
    TASK = "task"                        # "create a task to review X"
    CHAT = "chat"                        # General conversation, greetings
    CONTINUATION = "continuation"        # User is responding to a previous question
    UNKNOWN = "unknown"


@dataclass
class SkillContext:
    """
    Context passed to a skill - contains only what's needed.
    Skills declare what context they need, and ContextManager provides it.
    """
    # Always provided
    project_id: "UUID"
    project_title: str
    channel_id: "UUID"
    user_message: str

    # Session state (persisted between turns)
    current_skill: Optional[str] = None
    skill_state: SkillState = SkillState.IDLE
    skill_data: Dict[str, Any] = field(default_factory=dict)

    # Optional context - skills request what they need
    recent_search_results: Optional[List[Dict]] = None
    conversation_history: Optional[List[Dict]] = None  # Last N messages
    project_papers: Optional[List[Dict]] = None        # Papers in project
    project_references: Optional[List[Dict]] = None    # References in library
    project_info: Optional[Dict[str, Any]] = None      # Project objectives, scope, description


@dataclass
class SkillResult:
    """
    Result from a skill handler.
    Contains the response and next state for the conversation.
    """
    # Response to user
    message: str

    # State management
    next_state: SkillState
    state_data: Dict[str, Any] = field(default_factory=dict)  # Persist for next turn

    # Actions to execute (search, create paper, etc.)
    actions: List[Dict] = field(default_factory=list)

    # Optional metadata
    citations: List[Dict] = field(default_factory=list)
    model_used: Optional[str] = None
    reasoning_used: bool = False


@dataclass
class ClassifiedIntent:
    """Result of intent classification."""
    intent: Intent
    confidence: float
    params: Dict[str, Any] = field(default_factory=dict)  # Extracted parameters


class BaseSkill(ABC):
    """
    Base class for all skills.

    Each skill:
    - Handles a specific intent (search, create, edit, etc.)
    - Manages its own state machine for multi-turn flows
    - Has a focused prompt (not 100+ lines)
    - Declares what context it needs

    To add a new skill:
    1. Create a new class inheriting from BaseSkill
    2. Set name, description, handles_intents
    3. Implement handle() method
    4. Register in SkillRegistry
    """

    # Subclasses must define these
    name: str = "base"
    description: str = "Base skill"
    handles_intents: List[Intent] = []

    # What context this skill needs (ContextManager uses this)
    needs_search_results: bool = False
    needs_conversation_history: bool = False
    needs_project_papers: bool = False
    needs_project_references: bool = False

    def __init__(self, ai_service):
        self.ai_service = ai_service
        self.model = "gpt-5.2"

    @abstractmethod
    def handle(self, ctx: SkillContext) -> SkillResult:
        """
        Handle a user message.

        This is called when:
        1. A new message is classified to this skill's intent
        2. User is continuing a conversation with this skill (state != IDLE)

        Returns SkillResult with response and next state.
        """
        pass

    def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
        reasoning_effort: str = "low",
        max_tokens: int = 1000,
    ) -> str:
        """Helper to call LLM with a focused prompt."""
        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_message.strip()},
        ]

        response = self.ai_service.create_response(
            messages=messages,
            model=self.model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_tokens,
        )
        return self.ai_service.extract_response_text(response) or ""

    def _call_llm_with_history(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        reasoning_effort: str = "low",
        max_tokens: int = 1000,
    ) -> str:
        """Helper to call LLM with conversation history."""
        full_messages = [
            {"role": "system", "content": system_prompt.strip()},
            *messages,
        ]

        response = self.ai_service.create_response(
            messages=full_messages,
            model=self.model,
            reasoning_effort=reasoning_effort,
            max_output_tokens=max_tokens,
        )
        return self.ai_service.extract_response_text(response) or ""
