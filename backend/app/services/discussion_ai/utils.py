"""
Shared utility functions for the Discussion AI orchestrator.

Module-level pure functions and constants used across multiple mixin modules.
"""

from __future__ import annotations

import re
from typing import Dict

from app.constants.paper_templates import CONFERENCE_TEMPLATES

# Pre-compiled regex patterns (avoid recompilation per call)
_CITE_PATTERN = re.compile(r'\\cite\{([^}]+)\}')
_SECTION_PATTERN_CACHE: Dict[str, "re.Pattern[str]"] = {}

# LaTeX special characters that must be escaped in untrusted text
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
