"""LLM-based intent classifier for dynamic tool exposure.

Classifies user messages into intents to determine which tools to expose.
Called only when the deterministic policy returns "general" — saves latency
when regex already detects intent (direct_search, project_update).

Design:
- Sync only (2s hard timeout, acceptable for both sync and async paths)
- Graceful no-op when client is None (tests, missing API key)
- Strict validation: intent must be in VALID_INTENTS, confidence clamped [0,1]
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional, Tuple, List, Dict

logger = logging.getLogger(__name__)

VALID_INTENTS = frozenset({
    "direct_search", "analysis", "library", "writing", "project_update", "general"
})

CLASSIFIER_TIMEOUT = 2.0  # hard cap in seconds

DEFAULT_FALLBACK: Tuple[str, float] = ("general", 0.5)

CLASSIFIER_PROMPT = """Classify the user message into exactly one intent.
- direct_search: find/search for new papers externally
- analysis: compare, analyze, or identify gaps across papers
- library: view, manage, export, annotate, or search within saved library
- writing: create, write, edit, or update a paper/document/artifact
- project_update: change project description, keywords, or objectives
- general: greeting, acknowledgment, unclear, or doesn't fit above
Respond JSON only: {"intent": "...", "confidence": 0.0-1.0}"""

_JSON_RE = re.compile(r"\{[^}]+\}")


def _get_classifier_model() -> str:
    """Config fallback chain: settings.INTENT_CLASSIFIER_MODEL -> 'openai/gpt-4o-mini'."""
    try:
        from app.core.config import settings
        model = getattr(settings, "INTENT_CLASSIFIER_MODEL", None)
        if model:
            return model
    except Exception:
        pass
    return "openai/gpt-4o-mini"


def _parse_response(text: str) -> Tuple[str, float]:
    """Parse JSON response, validate intent enum, clamp confidence to [0,1].

    Returns DEFAULT_FALLBACK on any parse error.
    """
    if not text:
        return DEFAULT_FALLBACK

    # Extract JSON from text (model might wrap in markdown etc.)
    match = _JSON_RE.search(text)
    if not match:
        logger.debug("[IntentClassifier] No JSON found in response: %s", text[:200])
        return DEFAULT_FALLBACK

    try:
        data = json.loads(match.group())
    except (json.JSONDecodeError, ValueError):
        logger.debug("[IntentClassifier] JSON parse failed: %s", match.group()[:200])
        return DEFAULT_FALLBACK

    intent = data.get("intent", "")
    if intent not in VALID_INTENTS:
        logger.debug("[IntentClassifier] Invalid intent '%s', falling back", intent)
        return DEFAULT_FALLBACK

    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    confidence = max(0.0, min(1.0, confidence))
    return (intent, confidence)


def classify_intent_sync(
    message: str,
    conversation_tail: List[Dict],
    client,
    model: Optional[str] = None,
) -> Tuple[str, float]:
    """Classify user intent via a cheap LLM call (sync, 2s timeout).

    Args:
        message: Current user message
        conversation_tail: Last 2-4 messages for deictic context
        client: OpenAI-compatible sync client (or None to no-op)
        model: Override model ID (default: config or gpt-4o-mini)

    Returns:
        (intent, confidence) tuple. Falls back to DEFAULT_FALLBACK on any error.
    """
    if client is None:
        return DEFAULT_FALLBACK

    if not message or not message.strip():
        return DEFAULT_FALLBACK

    model = model or _get_classifier_model()

    # Build minimal messages for classification
    messages = [{"role": "system", "content": CLASSIFIER_PROMPT}]

    # Add conversation tail for deictic context ("this", "those", "more")
    for msg in (conversation_tail or [])[-4:]:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role in ("user", "assistant") and content:
            # Truncate to save tokens
            messages.append({"role": role, "content": content[:200]})

    messages.append({"role": "user", "content": message[:300]})

    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=30,
            temperature=0,
            timeout=CLASSIFIER_TIMEOUT,
        )
        text = response.choices[0].message.content or ""
        return _parse_response(text)
    except Exception as exc:
        logger.debug("[IntentClassifier] LLM call failed: %s", exc)
        return DEFAULT_FALLBACK
