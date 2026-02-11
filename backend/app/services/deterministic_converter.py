"""Fully deterministic LaTeX template converter.

Builds ALL <<<EDIT>>> blocks (preamble + body) in code — no LLM needed.
Returns ConvertResult with kind="edits", "noop", or "fallback".
"""

import logging
from dataclasses import dataclass
from typing import Literal, Optional

from app.constants.paper_templates import CONFERENCE_TEMPLATES

logger = logging.getLogger(__name__)

# Templates that don't use \maketitle (intentional fallback to LLM)
_NON_MAKETITLE_FAMILIES = {"elsevier"}


@dataclass
class ConvertResult:
    kind: Literal["edits", "noop", "fallback"]
    edits: str = ""
    fallback_reason: str = ""


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


def _is_commented(line: str, command_pos: int) -> bool:
    """Check if an unescaped % appears before command_pos on the line."""
    i = 0
    while i < command_pos:
        if line[i] == "%" and (i == 0 or line[i - 1] != "\\"):
            return True
        i += 1
    return False


def _find_command(line: str, command: str) -> int:
    """Find command in line, ensuring next char isn't alpha (precise match).

    The alpha check only applies when the command itself ends with an alpha char
    (prevents \\maketitle matching \\maketitlepage, but allows \\bibliographystyle{).
    Returns the index of the command start, or -1 if not found.
    """
    start = 0
    while True:
        idx = line.find(command, start)
        if idx < 0:
            return -1
        end = idx + len(command)
        if command[-1].isalpha() and end < len(line) and line[end].isalpha():
            start = end
            continue
        return idx


def _normalize_preamble(text: str) -> str:
    """Normalize preamble for comparison: strip whitespace, remove comment-only lines."""
    lines = []
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("%"):
            continue
        if stripped:
            lines.append(stripped)
    return "\n".join(lines)


def deterministic_full_convert(source: str, template_id: str) -> ConvertResult:
    """Build all <<<EDIT>>> blocks (preamble + body) deterministically.

    Returns ConvertResult — never None.
    """
    template = CONFERENCE_TEMPLATES.get(template_id)
    if not template:
        result = ConvertResult(kind="fallback", fallback_reason="unknown_template")
        logger.info("deterministic_convert: %s kind=%s edit_blocks=0 fallback_reason=%s",
                     template_id, result.kind, result.fallback_reason)
        return result

    # Non-\maketitle families (e.g. Elsevier) — intentional fallback
    if template_id in _NON_MAKETITLE_FAMILIES:
        result = ConvertResult(kind="fallback", fallback_reason="non_maketitle_family")
        logger.info("deterministic_convert: %s kind=%s edit_blocks=0 fallback_reason=%s",
                     template_id, result.kind, result.fallback_reason)
        return result

    # Guard: truncated source
    if r"\end{document}" not in source:
        result = ConvertResult(kind="fallback", fallback_reason="truncated")
        logger.info("deterministic_convert: %s kind=%s edit_blocks=0 fallback_reason=%s",
                     template_id, result.kind, result.fallback_reason)
        return result

    lines = source.split("\n")

    # Find \maketitle line (precise match, skip commented)
    maketitle_line = None
    for i, line in enumerate(lines, 1):
        cmd_pos = _find_command(line, r"\maketitle")
        if cmd_pos >= 0 and not _is_commented(line, cmd_pos):
            maketitle_line = i
            break
    if not maketitle_line:
        result = ConvertResult(kind="fallback", fallback_reason="missing_maketitle")
        logger.info("deterministic_convert: %s kind=%s edit_blocks=0 fallback_reason=%s",
                     template_id, result.kind, result.fallback_reason)
        return result

    # Extract title
    title = extract_latex_title(source)
    if not title:
        result = ConvertResult(kind="fallback", fallback_reason="missing_title")
        logger.info("deterministic_convert: %s kind=%s edit_blocks=0 fallback_reason=%s",
                     template_id, result.kind, result.fallback_reason)
        return result

    # --- Build edit blocks ---
    edit_blocks = []  # list of (start_line, edit_str)
    target_bib_style = template.get("bib_style", "plain")

    # --- Body edits (lines after \maketitle) ---
    bib_edited = False
    has_ieee_keywords = False
    for i in range(maketitle_line, len(lines)):  # 0-indexed: maketitle_line corresponds to line after \maketitle
        line = lines[i]
        line_num = i + 1  # 1-indexed

        # IEEEkeywords → keywords (skip when target is IEEE, which defines IEEEkeywords)
        if template_id != "ieee":
            begin_pos = _find_command(line, r"\begin{IEEEkeywords}")
            if begin_pos >= 0 and not _is_commented(line, begin_pos):
                has_ieee_keywords = True
                new_line = line[:begin_pos] + r"\begin{keywords}" + line[begin_pos + len(r"\begin{IEEEkeywords}"):]
                if new_line.strip() != line.strip():
                    anchor = line.strip()
                    edit_blocks.append((line_num, (
                        f"<<<EDIT>>>\n"
                        f"Replace IEEEkeywords begin\n"
                        f"<<<LINES>>>\n"
                        f"{line_num}-{line_num}\n"
                        f"<<<ANCHOR>>>\n"
                        f"{anchor}\n"
                        f"<<<PROPOSED>>>\n"
                        f"{new_line}\n"
                        f"<<<END>>>\n"
                    )))

            end_pos = _find_command(line, r"\end{IEEEkeywords}")
            if end_pos >= 0 and not _is_commented(line, end_pos):
                new_line = line[:end_pos] + r"\end{keywords}" + line[end_pos + len(r"\end{IEEEkeywords}"):]
                if new_line.strip() != line.strip():
                    anchor = line.strip()
                    edit_blocks.append((line_num, (
                        f"<<<EDIT>>>\n"
                        f"Replace IEEEkeywords end\n"
                        f"<<<LINES>>>\n"
                        f"{line_num}-{line_num}\n"
                        f"<<<ANCHOR>>>\n"
                        f"{anchor}\n"
                        f"<<<PROPOSED>>>\n"
                        f"{new_line}\n"
                        f"<<<END>>>\n"
                    )))

        # \bibliographystyle{X} → \bibliographystyle{target}
        if not bib_edited:
            bib_pos = _find_command(line, r"\bibliographystyle{")
            if bib_pos >= 0 and not _is_commented(line, bib_pos):
                bib_edited = True
                # Extract current style
                brace_start = bib_pos + len(r"\bibliographystyle{")
                brace_end = line.find("}", brace_start)
                if brace_end > brace_start:
                    current_style = line[brace_start:brace_end]
                    if current_style != target_bib_style:
                        new_line = line[:brace_start] + target_bib_style + line[brace_end:]
                        anchor = line.strip()
                        edit_blocks.append((line_num, (
                            f"<<<EDIT>>>\n"
                            f"Update bibliographystyle to {target_bib_style}\n"
                            f"<<<LINES>>>\n"
                            f"{line_num}-{line_num}\n"
                            f"<<<ANCHOR>>>\n"
                            f"{anchor}\n"
                            f"<<<PROPOSED>>>\n"
                            f"{new_line}\n"
                            f"<<<END>>>\n"
                        )))

    # --- Preamble edit ---
    target_preamble = template["preamble_example"].replace("Your Paper Title", title)

    # If source has IEEEkeywords and target isn't IEEEtran, inject keywords env definition
    if has_ieee_keywords and template_id != "ieee":
        # Insert before \begin{document}
        target_preamble = target_preamble.replace(
            r"\begin{document}",
            "\\newenvironment{keywords}{\\noindent\\textbf{Keywords:} }{\\par}\n\n\\begin{document}",
        )

    current_preamble = "\n".join(lines[:maketitle_line])  # lines 1..maketitle_line (inclusive)

    preamble_matches = _normalize_preamble(current_preamble) == _normalize_preamble(target_preamble)

    if not preamble_matches:
        anchor = next((l for l in lines[:5] if l.strip()), lines[0])
        edit_blocks.append((1, (
            f"<<<EDIT>>>\n"
            f"Replace preamble with {template_id.upper()} format\n"
            f"<<<LINES>>>\n"
            f"1-{maketitle_line}\n"
            f"<<<ANCHOR>>>\n"
            f"{anchor}\n"
            f"<<<PROPOSED>>>\n"
            f"{target_preamble}\n"
            f"<<<END>>>\n"
        )))

    # No edits needed
    if not edit_blocks:
        result = ConvertResult(kind="noop")
        logger.info("deterministic_convert: %s kind=%s edit_blocks=0 fallback_reason=",
                     template_id, result.kind)
        return result

    # Sort by descending start_line for safer sequential apply
    edit_blocks.sort(key=lambda x: x[0], reverse=True)

    combined = "\n".join(block for _, block in edit_blocks)
    result = ConvertResult(kind="edits", edits=combined)
    logger.info("deterministic_convert: %s kind=%s edit_blocks=%d fallback_reason=",
                 template_id, result.kind, len(edit_blocks))
    return result
