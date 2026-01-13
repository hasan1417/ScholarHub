"""
Conversation State Machine - Enforces hard rules via code.

The LLM CANNOT override these rules. This is the key difference from prompt-based control.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any, List
import logging

logger = logging.getLogger(__name__)


class ConversationPhase(str, Enum):
    """Deterministic conversation phases."""
    INITIAL = "initial"
    CLARIFICATION_PENDING = "clarification_pending"
    EXECUTING = "executing"
    COMPLETE = "complete"


class UserIntent(str, Enum):
    """User intent types."""
    # Clear intents - proceed immediately
    SEARCH_PAPERS = "search_papers"
    SEARCH_FROM_CONTEXT = "search_from_context"  # Search for papers about topics from conversation
    CREATE_CONTENT = "create_content"
    ASK_QUESTION = "ask_question"
    SIMPLE_CHAT = "simple_chat"

    # Requires clarification
    AMBIGUOUS_REQUEST = "ambiguous_request"

    # Follow-up intents
    CLARIFY_RESPONSE = "clarify_response"


@dataclass
class ConversationState:
    """
    Immutable snapshot of conversation state.
    Stored in DB and used to enforce rules.
    """
    phase: ConversationPhase = ConversationPhase.INITIAL
    clarification_asked: bool = False
    clarification_type: Optional[str] = None  # What we asked about
    original_query: Optional[str] = None
    original_intent: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phase": self.phase.value,
            "clarification_asked": self.clarification_asked,
            "clarification_type": self.clarification_type,
            "original_query": self.original_query,
            "original_intent": self.original_intent,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationState":
        if not data:
            return cls()
        return cls(
            phase=ConversationPhase(data.get("phase", "initial")),
            clarification_asked=data.get("clarification_asked", False),
            clarification_type=data.get("clarification_type"),
            original_query=data.get("original_query"),
            original_intent=data.get("original_intent"),
        )


@dataclass
class ClassifiedIntent:
    """Result of intent classification."""
    intent: UserIntent
    confidence: float = 1.0
    needs_project_context: bool = False
    needs_search_results: bool = False
    needs_library: bool = False
    extracted_topic: Optional[str] = None
    extracted_count: Optional[int] = None
    clarification_answer: Optional[str] = None  # What user chose
    extracted_context_query: Optional[str] = None  # Query extracted from conversation (for SEARCH_FROM_CONTEXT)


@dataclass
class StateTransition:
    """Result of a state transition - what the system should do."""
    new_state: ConversationState
    action: str  # "ask_clarification", "execute", "respond"
    prompt_constraints: Dict[str, Any] = field(default_factory=dict)
    context_to_include: List[str] = field(default_factory=list)


class ConversationStateMachine:
    """
    Enforces conversation rules via deterministic state transitions.

    KEY PRINCIPLE: The LLM's job is to generate content within boundaries.
    This state machine defines those boundaries - the LLM CANNOT override them.
    """

    # Intents that are always clear - never need clarification
    CLEAR_INTENTS = {
        UserIntent.SEARCH_PAPERS,
        UserIntent.SEARCH_FROM_CONTEXT,  # Search based on conversation context
        UserIntent.SIMPLE_CHAT,
        UserIntent.ASK_QUESTION,
        UserIntent.CLARIFY_RESPONSE,
    }

    # Intents that MAY need clarification (but only once)
    CLARIFIABLE_INTENTS = {
        UserIntent.AMBIGUOUS_REQUEST,
        UserIntent.CREATE_CONTENT,
    }

    def transition(
        self,
        current_state: ConversationState,
        classified_intent: ClassifiedIntent,
        message: str,
    ) -> StateTransition:
        """
        Compute the next state and required action.

        This is the CORE ENFORCEMENT MECHANISM:
        - If clarification was already asked, we CANNOT ask again
        - Clear intents always execute immediately
        """

        intent = classified_intent.intent

        logger.info(
            "State transition: phase=%s, clarification_asked=%s, intent=%s",
            current_state.phase.value,
            current_state.clarification_asked,
            intent.value,
        )

        # RULE 1: User is responding to our clarification
        if current_state.clarification_asked and intent == UserIntent.CLARIFY_RESPONSE:
            logger.info("User answered clarification - executing")
            return StateTransition(
                new_state=ConversationState(
                    phase=ConversationPhase.EXECUTING,
                    clarification_asked=True,
                    clarification_type=current_state.clarification_type,
                    original_query=current_state.original_query,
                    original_intent=current_state.original_intent,
                ),
                action="execute",
                prompt_constraints={
                    "no_questions_allowed": True,
                    "user_choice": message,  # What user selected
                    "original_query": current_state.original_query,
                },
                context_to_include=self._compute_context(classified_intent),
            )

        # RULE 2: Clear intents - execute immediately, NO clarification ever
        if intent in self.CLEAR_INTENTS:
            logger.info("Clear intent - executing immediately")
            return StateTransition(
                new_state=ConversationState(
                    phase=ConversationPhase.EXECUTING,
                    clarification_asked=False,
                    original_intent=intent.value,
                ),
                action="execute",
                prompt_constraints={
                    "no_clarification_questions": True,
                },
                context_to_include=self._compute_context(classified_intent),
            )

        # RULE 3: Ambiguous intent - ask clarification ONLY IF NOT ALREADY ASKED
        if intent in self.CLARIFIABLE_INTENTS:
            if current_state.clarification_asked:
                # HARD BLOCK: Already asked, must proceed with best guess
                logger.info("Clarification already asked - forcing execution")
                return StateTransition(
                    new_state=ConversationState(
                        phase=ConversationPhase.EXECUTING,
                        clarification_asked=True,
                        original_query=current_state.original_query,
                        original_intent=current_state.original_intent,
                    ),
                    action="execute",
                    prompt_constraints={
                        "no_questions_allowed": True,
                        "make_reasonable_choice": True,
                    },
                    context_to_include=self._compute_context(classified_intent),
                )
            else:
                # First time - allowed to ask ONE clarification
                logger.info("First ambiguous request - allowing clarification")
                clarification_type = self._determine_clarification_type(intent, message)
                return StateTransition(
                    new_state=ConversationState(
                        phase=ConversationPhase.CLARIFICATION_PENDING,
                        clarification_asked=True,
                        clarification_type=clarification_type,
                        original_query=message,
                        original_intent=intent.value,
                    ),
                    action="ask_clarification",
                    prompt_constraints={
                        "clarification_type": clarification_type,
                        "max_options": 2,
                        "keep_short": True,
                    },
                    context_to_include=[],  # No context for clarification
                )

        # Default: Execute with response
        logger.info("Default - generating response")
        return StateTransition(
            new_state=ConversationState(
                phase=ConversationPhase.COMPLETE,
                clarification_asked=False,
                original_intent=intent.value,
            ),
            action="respond",
            prompt_constraints={},
            context_to_include=self._compute_context(classified_intent),
        )

    def _compute_context(self, classified_intent: ClassifiedIntent) -> List[str]:
        """Determine what context to include based on intent classification."""
        context = []
        if classified_intent.needs_project_context:
            context.append("project")
        if classified_intent.needs_search_results:
            context.append("search_results")
        if classified_intent.needs_library:
            context.append("library")
        return context

    def _determine_clarification_type(self, intent: UserIntent, message: str) -> str:
        """Determine what kind of clarification to ask."""
        msg_lower = message.lower()

        if "topic" in msg_lower:
            return "papers_or_topics"
        if "information" in msg_lower or "info" in msg_lower:
            return "papers_or_summary"
        if intent == UserIntent.CREATE_CONTENT:
            return "content_type"

        return "general"
