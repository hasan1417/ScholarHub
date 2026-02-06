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


def _normalize_title(t: str) -> str:
    """Normalize a title for duplicate comparison: lowercase, strip whitespace/punctuation."""
    t = (t or "").lower().strip()
    t = re.sub(r'\s+', ' ', t)
    t = re.sub(r'[^\w\s]', '', t)
    return t


def _normalize_author(a: str) -> str:
    """Normalize an author name for comparison: extract last name, lowercase."""
    return (a or "").lower().strip().split()[-1] if a and a.strip() else ""
