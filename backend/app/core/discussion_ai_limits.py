"""Shared request and runtime limits for Discussion AI conversation history."""

CONVERSATION_HISTORY_MAX_ITEMS = 20
CONVERSATION_HISTORY_TOKEN_BUDGET = 16_000

# Match the conservative fallback used by discussion_ai.token_utils.
APPROXIMATE_CHARS_PER_TOKEN = 4
CONVERSATION_HISTORY_ITEM_MAX_CHARS = (
    CONVERSATION_HISTORY_TOKEN_BUDGET
    * APPROXIMATE_CHARS_PER_TOKEN
    // CONVERSATION_HISTORY_MAX_ITEMS
)
