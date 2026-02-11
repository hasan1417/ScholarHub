"""
Shared utility functions for the Discussion AI orchestrator.

Module-level pure functions and constants used across multiple mixin modules.
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)

from app.constants.paper_templates import CONFERENCE_TEMPLATES

# Pre-compiled regex patterns (avoid recompilation per call)
_CITE_PATTERN = re.compile(r'\\cite\{([^}]+)\}')
_SECTION_PATTERN_CACHE: Dict[str, "re.Pattern[str]"] = {}

# LaTeX special characters that must be escaped in untrusted text
MUTATING_TOOLS = frozenset({"update_project_info", "create_paper", "update_paper"})


def filter_duplicate_mutations(
    tool_calls: List[Dict],
    already_called: Set[Tuple[str, ...]],
) -> List[Dict]:
    """Filter out duplicate mutating tool calls within a single turn.

    Tracks by (tool_name, sorted_arg_key_value_pairs) so the same tool
    called with different arguments is allowed through, while an identical
    re-invocation (same name, same args, same values) is blocked.

    Returns the filtered list. Mutates *already_called* in-place.
    """
    filtered = []
    for tc in tool_calls:
        tool_name = tc.get("name", "")
        if tool_name in MUTATING_TOOLS:
            args = tc.get("arguments") or {}
            signature = (tool_name, *sorted((k, str(v)) for k, v in args.items()))
            if signature in already_called:
                logger.warning("[GuardRail] Blocked duplicate mutating tool call: %s", tool_name)
                continue
            already_called.add(signature)
        filtered.append(tc)
    return filtered


_LATEX_SPECIAL_CHARS = str.maketrans({
    '\\': r'\textbackslash{}',
    '{': r'\{',
    '}': r'\}',
    '$': r'\$',
    '&': r'\&',
    '#': r'\#',
    '%': r'\%',
    '_': r'\_',
    '^': r'\^{}',
    '~': r'\~{}',
})

# Available template IDs for create_paper tool
AVAILABLE_TEMPLATES = list(CONFERENCE_TEMPLATES.keys())


def _escape_latex(text: str) -> str:
    """Escape LaTeX special characters in untrusted text (titles, authors, etc.)."""
    if not text:
        return text
    return text.translate(_LATEX_SPECIAL_CHARS)


# Regex to strip ASCII control characters (except common whitespace)
_CONTROL_CHAR_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')


def sanitize_for_context(text: str, max_length: int = 500) -> str:
    """Sanitize untrusted text before embedding into AI system context.

    Prevents prompt injection by:
    1. Stripping control characters that could fake section boundaries
    2. Truncating to a safe length
    3. Collapsing excessive newlines that could push instructions out of view
    """
    if not text:
        return text
    text = _CONTROL_CHAR_RE.sub('', text)
    # Collapse 3+ consecutive newlines into 2
    text = re.sub(r'\n{3,}', '\n\n', text)
    if len(text) > max_length:
        text = text[:max_length] + '…'
    return text


def _normalize_title(t: str) -> str:
    """Normalize a title for duplicate comparison: lowercase, strip whitespace/punctuation."""
    t = (t or "").lower().strip()
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'[^\w\s]', '', t)
    return t


def _normalize_author(a: str) -> str:
    """Normalize an author name for comparison: extract last name, lowercase."""
    return (a or "").lower().strip().split()[-1] if a and a.strip() else ""
