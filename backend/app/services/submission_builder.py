"""Submission Package Builder — template-driven submission packaging for academic venues."""

import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Any, Set
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.reference import Reference

logger = logging.getLogger(__name__)

LATEX_STYLES_DIR = Path(__file__).parent.parent / "assets" / "latex_styles"

VENUE_CONFIGS: dict[str, dict[str, Any]] = {
    "ieee": {
        "name": "IEEE",
        "abstract_max_words": 250,
        "sections": [
            "Introduction",
            "Related Work",
            "Methodology",
            "Experiments",
            "Results",
            "Discussion",
            "Conclusion",
        ],
        "reference_style": "ieee",
        "file_structure": ["main.tex", "references.bib", "figures/"],
        "document_class": r"\documentclass[conference]{IEEEtran}",
        "required_packages": ["cite", "amsmath", "graphicx"],
        "font_size": "10pt",
    },
    "acm": {
        "name": "ACM",
        "abstract_max_words": 200,
        "sections": [
            "Introduction",
            "Related Work",
            "Methodology",
            "Evaluation",
            "Results",
            "Discussion",
            "Conclusion",
        ],
        "reference_style": "acm",
        "file_structure": ["main.tex", "references.bib", "figures/"],
        "document_class": r"\documentclass[sigconf]{acmart}",
        "required_packages": ["booktabs", "graphicx"],
        "font_size": "9pt",
    },
    "springer": {
        "name": "Springer LNCS",
        "abstract_max_words": 250,
        "sections": [
            "Introduction",
            "Background",
            "Methods",
            "Results",
            "Discussion",
            "Conclusion",
        ],
        "reference_style": "springer",
        "file_structure": ["main.tex", "references.bib", "figures/"],
        "document_class": r"\documentclass{llncs}",
        "required_packages": ["graphicx", "amsmath"],
        "font_size": "10pt",
    },
    "elsevier": {
        "name": "Elsevier",
        "abstract_max_words": 300,
        "sections": [
            "Introduction",
            "Literature Review",
            "Methodology",
            "Results",
            "Discussion",
            "Conclusion",
        ],
        "reference_style": "elsevier",
        "file_structure": ["main.tex", "references.bib", "figures/"],
        "document_class": r"\documentclass[review]{elsarticle}",
        "required_packages": ["natbib", "graphicx", "amsmath", "lineno"],
        "font_size": "12pt",
    },
    "arxiv": {
        "name": "arXiv",
        "abstract_max_words": None,
        "sections": None,
        "reference_style": "any",
        "file_structure": ["main.tex", "references.bib", "figures/"],
        "document_class": r"\documentclass[11pt]{article}",
        "required_packages": ["amsmath", "graphicx", "hyperref"],
        "font_size": "11pt",
    },
}

# Pre-compiled regex helpers
_SECTION_RE = re.compile(r"\\(?:section|subsection|subsubsection)\*?\{([^}]*)\}")
_ABSTRACT_BEGIN = re.compile(r"\\begin\{abstract\}", re.IGNORECASE)
_ABSTRACT_END = re.compile(r"\\end\{abstract\}", re.IGNORECASE)
_DOCCLASS_RE = re.compile(r"\\documentclass(\[.*?\])?\{([^}]+)\}")
_USEPACKAGE_RE = re.compile(r"\\usepackage(?:\[.*?\])?\{([^}]+)\}")
_COMMENT_RE = re.compile(r"(?<!\\)%.*$", re.MULTILINE)


def get_venue_configs() -> dict[str, dict[str, Any]]:
    """Return all venue configurations."""
    return VENUE_CONFIGS


def get_venue_config(venue: str) -> dict[str, Any] | None:
    """Return config for a specific venue (case-insensitive)."""
    return VENUE_CONFIGS.get(venue.lower())


def _strip_comments(source: str) -> str:
    return _COMMENT_RE.sub("", source)


def _extract_abstract(source: str) -> str:
    m_begin = _ABSTRACT_BEGIN.search(source)
    m_end = _ABSTRACT_END.search(source)
    if not m_begin or not m_end or m_end.start() <= m_begin.end():
        return ""
    raw = source[m_begin.end() : m_end.start()].strip()
    # Strip LaTeX commands for word counting
    t = re.sub(r"\\[a-zA-Z]+\*?\{", "", raw)
    t = t.replace("{", "").replace("}", "")
    t = re.sub(r"\\[a-zA-Z]+\*?", "", t)
    t = re.sub(r"[~$&^_#]", " ", t)
    return t


def _word_count(text: str) -> int:
    return len(text.split())


def validate_for_venue(latex_source: str, venue: str) -> list[dict]:
    """Check LaTeX source compliance against a venue's rules.

    Returns a list of issue dicts: {type, severity, message, passed}.
    """
    cfg = get_venue_config(venue)
    if not cfg:
        return [{"type": "venue", "severity": "error", "message": f"Unknown venue: {venue}", "passed": False}]

    issues: list[dict] = []
    clean = _strip_comments(latex_source)

    # 1. Document class check
    m_dc = _DOCCLASS_RE.search(clean)
    expected_dc = cfg["document_class"]
    if m_dc:
        actual_class = m_dc.group(2)
        # Extract the expected class name from \documentclass[...]{ClassName}
        expected_match = _DOCCLASS_RE.search(expected_dc)
        expected_class = expected_match.group(2) if expected_match else ""
        if actual_class == expected_class:
            issues.append({
                "type": "document_class",
                "severity": "info",
                "message": f"Document class '{actual_class}' matches {cfg['name']} requirements.",
                "passed": True,
            })
        else:
            issues.append({
                "type": "document_class",
                "severity": "warning",
                "message": f"Document class is '{actual_class}', but {cfg['name']} expects '{expected_class}'.",
                "passed": False,
            })
    else:
        issues.append({
            "type": "document_class",
            "severity": "error",
            "message": "No \\documentclass found in the source.",
            "passed": False,
        })

    # 2. Required packages
    used_packages: set[str] = set()
    for pkg_match in _USEPACKAGE_RE.finditer(clean):
        for pkg in pkg_match.group(1).split(","):
            used_packages.add(pkg.strip())

    for pkg in cfg.get("required_packages", []):
        if pkg in used_packages:
            issues.append({
                "type": "package",
                "severity": "info",
                "message": f"Required package '{pkg}' is included.",
                "passed": True,
            })
        else:
            issues.append({
                "type": "package",
                "severity": "warning",
                "message": f"Recommended package '{pkg}' is not included for {cfg['name']}.",
                "passed": False,
            })

    # 3. Abstract word count
    abstract_limit = cfg.get("abstract_max_words")
    abstract_text = _extract_abstract(clean)
    if abstract_text:
        wc = _word_count(abstract_text)
        if abstract_limit and wc > abstract_limit:
            issues.append({
                "type": "abstract",
                "severity": "warning",
                "message": f"Abstract is {wc} words (limit: {abstract_limit} for {cfg['name']}).",
                "passed": False,
            })
        elif abstract_limit:
            issues.append({
                "type": "abstract",
                "severity": "info",
                "message": f"Abstract is {wc} words (within {abstract_limit} word limit).",
                "passed": True,
            })
        else:
            issues.append({
                "type": "abstract",
                "severity": "info",
                "message": f"Abstract is {wc} words (no limit for {cfg['name']}).",
                "passed": True,
            })
    else:
        issues.append({
            "type": "abstract",
            "severity": "warning",
            "message": "No abstract found. Most venues require an abstract.",
            "passed": False,
        })

    # 4. Section structure
    expected_sections = cfg.get("sections")
    if expected_sections:
        found_sections = [s.strip() for s in _SECTION_RE.findall(clean)]
        found_lower = [s.lower() for s in found_sections]
        for sec in expected_sections:
            if sec.lower() in found_lower:
                issues.append({
                    "type": "section",
                    "severity": "info",
                    "message": f"Section '{sec}' found.",
                    "passed": True,
                })
            else:
                issues.append({
                    "type": "section",
                    "severity": "info",
                    "message": f"Recommended section '{sec}' not found (optional).",
                    "passed": False,
                })

    # 5. Bibliography check
    has_bib = r"\bibliography{" in clean or r"\printbibliography" in clean or r"\begin{thebibliography}" in clean
    if has_bib:
        issues.append({
            "type": "bibliography",
            "severity": "info",
            "message": "Bibliography command found.",
            "passed": True,
        })
    else:
        issues.append({
            "type": "bibliography",
            "severity": "warning",
            "message": "No bibliography command found. Ensure references are included.",
            "passed": False,
        })

    return issues


def _make_bibtex_key(title: str | None, authors: list | None, year: int | None) -> str:
    try:
        last = ""
        if isinstance(authors, list) and authors:
            parts = str(authors[0]).split()
            last = parts[-1].lower() if parts else ""
        yr = str(year or "")
        base = (title or "").strip().lower()
        base = "".join(ch for ch in base if ch.isalnum() or ch.isspace()).split()
        short = "".join(base[:3])[:12]
        key = (last + yr + short) or ("ref" + yr)
        return key
    except Exception:
        return "ref"


def _esc(s: str | None) -> str | None:
    if not s:
        return s
    # Escape special BibTeX characters
    s = s.replace("\\", "\\\\")
    for ch in ("#", "%", "&", "$", "_", "{", "}"):
        s = s.replace(ch, f"\\{ch}")
    return s


def _to_bibtex_entry(ref: Reference, seen_keys: Set[str]) -> str:
    key = _make_bibtex_key(ref.title, ref.authors, ref.year)
    original_key = key
    suffix_idx = 0
    while key in seen_keys:
        suffix_idx += 1
        key = original_key + chr(ord("a") + suffix_idx - 1)
    seen_keys.add(key)

    fields: list[str] = []

    def add(k: str, v: str | None) -> None:
        if v:
            fields.append(f"  {k} = {{{_esc(v)}}}")

    add("title", ref.title)
    if ref.authors and len(ref.authors) > 0:
        try:
            add("author", " and ".join(ref.authors))
        except Exception:
            pass
    add("year", str(ref.year) if ref.year else None)
    add("doi", ref.doi)
    add("url", ref.url)
    add("journal", ref.journal)

    entry_type = "article" if ref.journal else "misc"
    return f"@{entry_type}" + "{" + key + ",\n" + ",\n".join(fields) + "\n}"


def _generate_bibtex(db: Session, user_id: UUID, paper_id: str) -> str:
    refs = db.query(Reference).filter(
        Reference.owner_id == user_id,
        Reference.paper_id == paper_id,
    ).all()
    entries: list[str] = []
    seen_keys: Set[str] = set()
    for r in refs:
        try:
            entries.append(_to_bibtex_entry(r, seen_keys))
        except Exception as e:
            logger.warning("Failed to generate BibTeX entry for reference %s: %s", r.id, e)
    return "\n\n".join(entries) if entries else "% No references found."


def _build_readme(venue: str, cfg: dict) -> str:
    lines = [
        f"Submission Package — {cfg['name']}",
        "=" * 40,
        "",
        "Checklist before submission:",
        "",
        f"  [ ] Document class: {cfg['document_class']}",
    ]
    if cfg.get("abstract_max_words"):
        lines.append(f"  [ ] Abstract within {cfg['abstract_max_words']} words")
    if cfg.get("required_packages"):
        lines.append(f"  [ ] Required packages: {', '.join(cfg['required_packages'])}")
    if cfg.get("reference_style"):
        lines.append(f"  [ ] Reference style: {cfg['reference_style']}")
    if cfg.get("font_size"):
        lines.append(f"  [ ] Font size: {cfg['font_size']}")
    if cfg.get("sections"):
        lines.append(f"  [ ] Sections: {', '.join(cfg['sections'])}")
    if cfg.get("page_limit"):
        lines.append(f"  [ ] Page limit: {cfg['page_limit']}")

    lines += [
        "",
        "Files included:",
        "  - main.tex          (your manuscript)",
        "  - references.bib    (bibliography)",
        "  - figures/           (if any)",
        "  - README.txt        (this file)",
        "",
        "Generated by ScholarHub",
    ]
    return "\n".join(lines)


def build_submission_package(
    latex_source: str,
    venue: str,
    paper_id: str | None,
    extra_files: dict[str, str] | None,
    db: Session,
    user_id: UUID,
) -> bytes:
    """Build a ZIP file for venue submission.

    Returns the ZIP content as bytes.
    """
    cfg = get_venue_config(venue)
    if not cfg:
        raise ValueError(f"Unknown venue: {venue}")

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1. main.tex
        zf.writestr("main.tex", latex_source)

        # 2. Extra .tex files
        if extra_files:
            for fname, content in extra_files.items():
                safe_name = Path(fname).name
                if not safe_name.endswith(".tex") or safe_name == "main.tex":
                    continue
                zf.writestr(safe_name, content)

        # 3. references.bib
        if paper_id:
            bib_content = _generate_bibtex(db, user_id, paper_id)
            zf.writestr("references.bib", bib_content)

        # 4. Figures
        if paper_id:
            figures_dir = Path("uploads") / "papers" / paper_id / "figures"
            if figures_dir.exists():
                for fig_file in figures_dir.rglob("*"):
                    if fig_file.is_file():
                        arcname = "figures/" + fig_file.relative_to(figures_dir).as_posix()
                        zf.write(str(fig_file), arcname)

        # 5. Style files from bundled assets
        if LATEX_STYLES_DIR.exists():
            for style_file in LATEX_STYLES_DIR.glob("*"):
                if style_file.suffix in (".sty", ".bst", ".cls"):
                    zf.write(str(style_file), style_file.name)

        # 6. README.txt
        readme = _build_readme(venue, cfg)
        zf.writestr("README.txt", readme)

    return buf.getvalue()
