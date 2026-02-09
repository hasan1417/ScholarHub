"""
Lite/Full Route Classifier for Discussion AI

Classifies each user message as "lite" or "full" to skip the expensive
tool pipeline for trivial messages (greetings, acknowledgments, short
confirmations). Conservative: defaults to "full" when uncertain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional

@dataclass(frozen=True)
class RouteDecision:
    route: Literal["lite", "full"]
    reason: str

# Patterns that always require full pipeline
_ACTION_VERBS = re.compile(
    r"\b(find|search|create|write|draft|compare|analyze|ingest|add|update|"
    r"help|suggest|explain|summarize|review|plan|recommend|generate|export|annotate)\b",
    re.IGNORECASE,
)
_RESEARCH_TERMS = re.compile(
    r"\b(papers?|references?|library|abstract|methodology|literature|citation|"
    r"research|study|studies|thesis|dissertation|journal|article)\b",
    re.IGNORECASE,
)
_GREETING_PATTERNS = re.compile(
    r"^(hi|hello|hey|thanks|thx|thanx|thank you|ok|okay|cool|great|got it|"
    r"sounds good|makes sense|i see|understood|noted|nice|perfect|awesome|sure|alright|"
    r"no problem|no worries|right|yep|nope|cheers|good morning|good afternoon|good evening|"
    r"bye|goodbye|see ya|later|k bye|cya)"
    r"(?:[.!,\s].*)?$",
    re.IGNORECASE,
)
# Confirmations that imply pending action ("yes", "do it", "go ahead")
_CONFIRMATION_PATTERNS = re.compile(
    r"^(yes|yeah|yep|yup|do it|go ahead|please do|all of them|go for it|"
    r"let's do it|proceed|continue|absolutely|definitely|for sure)[.!,\s]*$",
    re.IGNORECASE,
)


def _last_assistant_suggested_action(conversation_history: List[Dict[str, str]]) -> bool:
    """Check if the last assistant message suggested a tool action."""
    for msg in reversed(conversation_history):
        if msg.get("role") == "assistant":
            text = (msg.get("content") or "").lower()
            action_hints = (
                "shall i", "should i", "want me to", "i can",
                "would you like me to", "ready to", "i'll",
                "let me know if", "do you want",
            )
            return any(hint in text for hint in action_hints)
    return False


def _last_turn_had_tool_action(
    conversation_history: List[Dict[str, str]],
    memory_facts: Optional[Dict[str, Any]] = None,
) -> bool:
    """Check if the last turn involved tool calls — using state, not text heuristics.

    Option 1: Check memory for _last_tools_called (set by orchestrator after each turn).
    Option 2: Fallback — check conversation metadata for tool result markers.
    """
    if memory_facts and memory_facts.get("_last_tools_called"):
        return True
    # Fallback: check conversation for tool call metadata
    for msg in reversed(conversation_history):
        if msg.get("role") == "assistant" and msg.get("tools_called"):
            return True
    return False


def classify_route(
    user_message: str,
    conversation_history: List[Dict[str, str]],
    memory_facts: Dict[str, Any],
) -> RouteDecision:
    """Classify a user message as needing 'lite' or 'full' AI pipeline.

    Conservative: defaults to 'full' when uncertain. False-positive lites
    (routing a real request to lite) are worse than false-positive fulls.
    """
    msg = (user_message or "").strip()
    if not msg:
        return RouteDecision("lite", "empty_message")

    # --- Full triggers (check first - conservative) ---

    if "?" in msg:
        return RouteDecision("full", "contains_question_mark")

    if _ACTION_VERBS.search(msg):
        return RouteDecision("full", "action_verb_detected")

    if _RESEARCH_TERMS.search(msg):
        return RouteDecision("full", "research_term_detected")

    if len(msg) > 80:
        return RouteDecision("full", "long_message")

    # Confirmations -> full if assistant suggested an action
    if _CONFIRMATION_PATTERNS.match(msg):
        if _last_assistant_suggested_action(conversation_history):
            return RouteDecision("full", "confirmation_of_pending_action")
        # Pure confirmation without pending action -> lite
        return RouteDecision("lite", "standalone_confirmation")

    # --- Lite triggers ---

    if _GREETING_PATTERNS.match(msg):
        return RouteDecision("lite", "greeting_or_acknowledgment")

    # Short follow-up after tool action -> full (state-based, not text heuristic)
    # "more plz" after a search should stay full, not drop to lite
    if len(msg) <= 20 and _last_turn_had_tool_action(conversation_history, memory_facts):
        return RouteDecision("full", "short_followup_after_action")

    if len(msg) <= 20:
        return RouteDecision("lite", "short_message")

    # Default: full (conservative)
    return RouteDecision("full", "default_full")
