"""Deterministic preamble converter for LaTeX template conversion.

Builds the preamble <<<EDIT>>> block in code (no LLM), then lets the LLM
handle body-level cleanup only.  Returns None on any ambiguity so the
caller can fall back to the full-LLM path.
"""

from typing import Optional

from app.constants.paper_templates import CONFERENCE_TEMPLATES


def extract_latex_title(source: str) -> Optional[str]:
    """Extract title from \\title{...} with brace matching."""
    idx = source.find(r"\title{")
    if idx < 0:
        return None
    start = idx + len(r"\title{")
    depth, pos = 1, start
    while pos < len(source) and depth > 0:
        if source[pos] == "{":
            depth += 1
        elif source[pos] == "}":
            depth -= 1
        pos += 1
    if depth != 0:
        return None
    return source[start : pos - 1].strip()


def deterministic_preamble_convert(source: str, template_id: str) -> Optional[str]:
    """Build preamble <<<EDIT>>> block deterministically.

    Returns None on any ambiguity so the caller falls back to the full-LLM path.
    """
    template = CONFERENCE_TEMPLATES.get(template_id)
    if not template:
        return None

    # Guard: truncated source → fallback
    if r"\end{document}" not in source:
        return None

    lines = source.split("\n")

    # Find \maketitle line
    maketitle_line = None
    for i, line in enumerate(lines, 1):
        if r"\maketitle" in line:
            maketitle_line = i
            break
    if not maketitle_line:
        return None

    # Extract title
    title = extract_latex_title(source)
    if not title:
        return None

    # Build target preamble with real title
    preamble = template["preamble_example"].replace("Your Paper Title", title)

    # Anchor: first non-empty line
    anchor = next((l for l in lines[:5] if l.strip()), lines[0])

    return (
        f"<<<EDIT>>>\n"
        f"Replace preamble with {template_id.upper()} format\n"
        f"<<<LINES>>>\n"
        f"1-{maketitle_line}\n"
        f"<<<ANCHOR>>>\n"
        f"{anchor}\n"
        f"<<<PROPOSED>>>\n"
        f"{preamble}\n"
        f"<<<END>>>\n"
    )
