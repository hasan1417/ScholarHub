"""
Lite/Full Route Classifier for Discussion AI

Classifies each user message as "lite" or "full" to skip the expensive
tool pipeline for trivial messages (greetings, acknowledgments).

Hybrid approach:
  - Regex fast-path for obvious cases (free, instant)
  - LLM classifier for the ambiguous middle zone (~50ms, ~$0.0001)
  - Conservative: defaults to "full" when uncertain
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Literal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RouteDecision:
    route: Literal["lite", "full"]
    reason: str


# ── Regex fast-paths (free, instant) ────────────────────────────────

# Action verbs → always full
_ACTION_VERBS = re.compile(
    r"\b(find|search|create|write|draft|compare|analyze|ingest|add|update|"
    r"help|suggest|explain|summarize|review|plan|recommend|generate|export|annotate)\b",
    re.IGNORECASE,
)

# Research terms → always full
_RESEARCH_TERMS = re.compile(
    r"\b(papers?|references?|library|abstract|methodology|literature|citation|"
    r"research|study|studies|thesis|dissertation|journal|article)\b",
    re.IGNORECASE,
)

# Question starters → always full ("what about GPT", "how does X work")
_QUESTION_START = re.compile(
    r"^(what|how|why|when|where|who|which|can|could|should|would|does|do|is|are)\b",
    re.IGNORECASE,
)

# Pure greetings: the ENTIRE message is just a greeting/ack, nothing else.
# Unlike the old pattern, this does NOT match compound messages like
# "thanks, now tell me about X".
_PURE_LITE = re.compile(
    r"^(?:hi|hello|hey|thanks|thx|thanx|thank you|ok|okay|cool|great|got it|"
    r"makes sense|i see|understood|noted|nice|awesome|sure|alright|"
    r"no problem|no worries|right|nope|cheers|good morning|good afternoon|"
    r"good evening|bye|goodbye|see ya|later|k bye|cya)"
    r"[.!,\s]*$",
    re.IGNORECASE,
)


# ── LLM classifier prompt ──────────────────────────────────────────

_ROUTE_PROMPT = (
    'Does this message need the research assistant\'s full capabilities '
    '(tools, search, analysis, answering questions), or is it just a casual exchange?\n'
    'Reply with exactly one word: "full" or "lite"\n\n'
    '"full" = question, request, instruction, feedback, follow-up, or anything substantive\n'
    '"lite" = ONLY a simple greeting, thanks, or acknowledgment with no additional request'
)


def _get_classifier_model() -> str:
    try:
        from app.core.config import settings
        model = getattr(settings, "ROUTE_CLASSIFIER_MODEL", None)
        if model:
            return model
    except Exception:
        pass
    return "openai/gpt-5-mini"


def _classify_with_llm(
    msg: str,
    conversation_history: List[Dict[str, str]],
    client: Any,
) -> RouteDecision:
    """Use a cheap LLM call to classify ambiguous messages."""
    try:
        messages = [{"role": "system", "content": _ROUTE_PROMPT}]

        # Last 2 messages for deictic context ("more on that", "try that instead")
        for m in (conversation_history or [])[-2:]:
            role = m.get("role", "user")
            content = (m.get("content") or "")[:150]
            if role in ("user", "assistant") and content:
                messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": msg[:200]})

        response = client.chat.completions.create(
            model=_get_classifier_model(),
            messages=messages,
            max_tokens=128,
            temperature=0,
            timeout=2.0,
            extra_body={"reasoning_effort": "low"},
        )
        text = (response.choices[0].message.content or "").strip().lower()

        if "lite" in text:
            return RouteDecision("lite", "llm_lite")
        # "full" or anything else → full (conservative)
        return RouteDecision("full", "llm_full")

    except Exception as exc:
        logger.debug("[RouteClassifier] LLM failed: %s — defaulting to full", exc)
        return RouteDecision("full", "llm_error_fallback")


# ── Public API ──────────────────────────────────────────────────────

def classify_route(
    user_message: str,
    conversation_history: List[Dict[str, str]],
    memory_facts: Dict[str, Any],
    client: Any = None,
) -> RouteDecision:
    """Classify a user message as needing 'lite' or 'full' AI pipeline.

    Args:
        client: Optional OpenAI-compatible sync client for LLM classification
                of ambiguous messages. When None, falls back to regex-only.
    """
    msg = (user_message or "").strip()
    if not msg:
        return RouteDecision("lite", "empty_message")

    # ── Definite FULL (regex fast-path) ──────────────────────────────
    if "?" in msg:
        return RouteDecision("full", "contains_question_mark")

    if _ACTION_VERBS.search(msg):
        return RouteDecision("full", "action_verb_detected")

    if _RESEARCH_TERMS.search(msg):
        return RouteDecision("full", "research_term_detected")

    if _QUESTION_START.match(msg):
        return RouteDecision("full", "question_start")

    if len(msg) > 80:
        return RouteDecision("full", "long_message")

    # ── Definite LITE (regex fast-path) ──────────────────────────────
    # Only when the ENTIRE message is a greeting/ack, nothing else.
    if _PURE_LITE.match(msg):
        return RouteDecision("lite", "pure_greeting")

    # ── Ambiguous zone ───────────────────────────────────────────────
    # Short messages, compound confirmations, follow-ups without clear
    # action verbs or research terms. LLM handles these accurately.
    if client:
        return _classify_with_llm(msg, conversation_history, client)

    # ── No client: conservative fallback (always full) ───────────────
    return RouteDecision("full", "default_full")
