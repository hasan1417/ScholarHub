"""
Token counting utilities for context window management.

Uses tiktoken for accurate token counting with model-aware context limits.
"""

import logging
from typing import Dict, List, Optional, Tuple

import tiktoken

logger = logging.getLogger(__name__)

# Hardcoded fallback limits — used only when OpenRouter API data is unavailable.
# These are conservative estimates leaving room for response generation.
_FALLBACK_CONTEXT_LIMITS: Dict[str, int] = {
    "openai/gpt-4o": 120000,
    "openai/gpt-4o-mini": 120000,
    "openai/gpt-4-turbo": 120000,
    "openai/gpt-4": 8000,
    "openai/gpt-3.5-turbo": 14000,
    "openai/o1": 120000,
    "openai/gpt-5.2-20251211": 120000,
    "anthropic/claude-3.5-sonnet": 190000,
    "anthropic/claude-sonnet-4": 190000,
    "anthropic/claude-opus-4": 190000,
    "google/gemini-pro-1.5": 1000000,
    "deepseek/deepseek-chat": 60000,
    "deepseek/deepseek-r1": 60000,
}

# Default limit for unknown models (conservative)
DEFAULT_CONTEXT_LIMIT = 28000

# Dynamic limits populated from OpenRouter API at runtime
_dynamic_context_limits: Dict[str, int] = {}


def update_context_limits(limits: Dict[str, int]) -> None:
    """Update dynamic context limits from API metadata (called by openrouter_orchestrator)."""
    _dynamic_context_limits.update(limits)

# Reserve tokens for response generation
RESPONSE_TOKEN_RESERVE = 4000

# Reserve tokens for tool outputs (they can be large)
TOOL_OUTPUT_RESERVE = 8000

# Threshold to trigger summarization (percentage of context used)
SUMMARIZATION_THRESHOLD = 0.80

# Cached encoders
_encoder_cache: Dict[str, tiktoken.Encoding] = {}


def get_encoder(model: str = "gpt-4") -> tiktoken.Encoding:
    """Get a tiktoken encoder, with caching.

    Uses cl100k_base encoding which works for most modern models.
    Falls back gracefully if tiktoken fails.
    """
    cache_key = "cl100k_base"  # Use same encoder for all models (good approximation)

    if cache_key not in _encoder_cache:
        try:
            _encoder_cache[cache_key] = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to load tiktoken encoder: {e}")
            # Return a minimal fallback that estimates ~4 chars per token
            return _FallbackEncoder()

    return _encoder_cache[cache_key]


class _FallbackEncoder:
    """Fallback encoder when tiktoken is unavailable."""

    def encode(self, text: str) -> range:
        # Rough estimate: ~4 characters per token
        return range(len(text) // 4)


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """Count tokens in a string."""
    if not text:
        return 0
    encoder = get_encoder(model)
    return len(encoder.encode(text))


def count_message_tokens(message: Dict[str, str], model: str = "gpt-4") -> int:
    """Count tokens in a message dict (role + content).

    Adds overhead for message formatting (~4 tokens per message).
    """
    content = message.get("content", "")
    role = message.get("role", "")

    tokens = count_tokens(content, model)
    tokens += count_tokens(role, model)
    tokens += 4  # Message formatting overhead

    return tokens


def count_messages_tokens(messages: List[Dict[str, str]], model: str = "gpt-4") -> int:
    """Count total tokens across all messages."""
    total = 0
    for msg in messages:
        total += count_message_tokens(msg, model)
    total += 2  # Conversation overhead
    return total


def get_context_limit(model: str) -> int:
    """Get the context limit for a model.

    Checks dynamic limits (from OpenRouter API) first, then hardcoded fallbacks.
    """
    # 1. Dynamic limits from API (most accurate, auto-updated)
    if model in _dynamic_context_limits:
        return _dynamic_context_limits[model]

    # 2. Hardcoded fallback — exact match
    if model in _FALLBACK_CONTEXT_LIMITS:
        return _FALLBACK_CONTEXT_LIMITS[model]

    # 3. Prefix matching (longest first) across both dynamic and fallback
    all_limits = {**_FALLBACK_CONTEXT_LIMITS, **_dynamic_context_limits}
    best_match = None
    best_len = 0
    for model_pattern, limit in all_limits.items():
        prefix = model_pattern.rsplit("-", 1)[0]
        if model.startswith(prefix) and len(prefix) > best_len:
            best_match = limit
            best_len = len(prefix)

    return best_match if best_match is not None else DEFAULT_CONTEXT_LIMIT


def get_available_context(
    model: str,
    system_tokens: int = 0,
    reserve_for_response: bool = True,
    reserve_for_tools: bool = True,
) -> int:
    """Calculate available tokens for conversation history.

    Args:
        model: Model identifier
        system_tokens: Tokens already used by system prompt
        reserve_for_response: Whether to reserve space for response
        reserve_for_tools: Whether to reserve space for tool outputs

    Returns:
        Available tokens for conversation history
    """
    limit = get_context_limit(model)

    available = limit - system_tokens

    if reserve_for_response:
        available -= RESPONSE_TOKEN_RESERVE

    if reserve_for_tools:
        available -= TOOL_OUTPUT_RESERVE

    return max(available, 1000)  # Minimum 1000 tokens


def fit_messages_in_budget(
    messages: List[Dict[str, str]],
    budget: int,
    model: str = "gpt-4",
    keep_newest: bool = True,
) -> Tuple[List[Dict[str, str]], int]:
    """Fit as many messages as possible within a token budget.

    Args:
        messages: List of message dicts
        budget: Maximum tokens to use
        model: Model for token counting
        keep_newest: If True, keep newest messages; if False, keep oldest

    Returns:
        (fitted_messages, tokens_used)
    """
    if not messages:
        return [], 0

    # Calculate tokens for each message
    message_tokens = [(msg, count_message_tokens(msg, model)) for msg in messages]

    # If keeping newest, reverse so we process from newest to oldest
    if keep_newest:
        message_tokens = list(reversed(message_tokens))

    fitted = []
    tokens_used = 0

    for msg, tokens in message_tokens:
        if tokens_used + tokens <= budget:
            fitted.append(msg)
            tokens_used += tokens
        else:
            break

    # Reverse back if we kept newest
    if keep_newest:
        fitted = list(reversed(fitted))

    return fitted, tokens_used


def should_summarize(
    messages: List[Dict[str, str]],
    model: str,
    system_tokens: int = 0,
) -> bool:
    """Check if conversation should be summarized based on token usage."""
    total_tokens = count_messages_tokens(messages, model)
    limit = get_context_limit(model)

    # Calculate usage ratio
    total_used = total_tokens + system_tokens + RESPONSE_TOKEN_RESERVE
    usage_ratio = total_used / limit

    return usage_ratio > SUMMARIZATION_THRESHOLD


def truncate_content(content: str, max_tokens: int, model: str = "gpt-4") -> str:
    """Truncate content to fit within token limit.

    Tries to truncate at sentence boundaries when possible.
    """
    current_tokens = count_tokens(content, model)

    if current_tokens <= max_tokens:
        return content

    # Binary search for the right length
    encoder = get_encoder(model)
    tokens = encoder.encode(content)

    # Truncate tokens
    truncated_tokens = tokens[:max_tokens - 10]  # Leave room for "..."

    try:
        truncated = encoder.decode(truncated_tokens)
    except Exception:
        # Fallback: character-based truncation
        ratio = max_tokens / current_tokens
        truncated = content[:int(len(content) * ratio)]

    # Try to end at a sentence boundary
    for boundary in [". ", ".\n", "! ", "? "]:
        last_boundary = truncated.rfind(boundary)
        if last_boundary > len(truncated) * 0.7:  # Don't truncate more than 30%
            truncated = truncated[:last_boundary + 1]
            break

    return truncated.strip() + "..."
