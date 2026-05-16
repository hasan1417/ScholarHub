"""Server-side validation for LaTeX citation keys in AI output."""

from __future__ import annotations

import logging
import re
from typing import Any, List, Optional, Set, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_CITE_COMMAND_RE = re.compile(r"\\(?P<command>cite(?:t|p)?\*?)\{(?P<keys>[^}]*)\}")
_VALID_FILTER_MODES = {"off", "warn", "strict"}


def make_bib_key(ref: dict) -> str:
    """Mirror frontend/src/components/editor/utils/bibKey.ts makeBibKey."""
    try:
        authors = ref.get("authors")
        first = str(authors[0]) if isinstance(authors, list) and len(authors) > 0 else ""
        first_parts = [part for part in re.split(r"\s+", first) if part]
        last_token = first_parts[-1] if first_parts else ""
        last = last_token.lower()
        yr = str(ref.get("year")) if ref.get("year") else ""
        base = re.sub(r"[^a-z0-9\s]", " ", (ref.get("title") or "").lower())
        parts = [part for part in re.split(r"\s+", base) if part]
        short = "".join(parts[:3])[:12]
        key = (last + yr + short) or ("ref" + yr)
        return key
    except Exception:
        return "ref"


def extract_cite_keys(text: str) -> List[Tuple[str, int, int, str]]:
    """Return (key, span_start, span_end, command) for supported citation commands."""
    results: List[Tuple[str, int, int, str]] = []
    for match in _CITE_COMMAND_RE.finditer(text or ""):
        keys_text = match.group("keys")
        keys_start = match.start("keys")
        cursor = 0
        for raw_key in keys_text.split(","):
            raw_start = cursor
            raw_end = raw_start + len(raw_key)
            key = raw_key.strip()
            if key:
                span_start = keys_start + raw_start + (len(raw_key) - len(raw_key.lstrip()))
                span_end = keys_start + raw_start + len(raw_key.rstrip())
                results.append((key, span_start, span_end, "\\" + match.group("command")))
            cursor = raw_end + 1
    return results


def filter_response(text: str, allowed_keys: Set[str]) -> Tuple[str, List[dict]]:
    """Replace every citation key not present in allowed_keys with a missing marker."""
    invalid: List[dict] = []
    allowed = set(allowed_keys or set())

    def replace_match(match: re.Match[str]) -> str:
        keys_text = match.group("keys")
        keys_start = match.start("keys")
        command = "\\" + match.group("command")
        replacement_keys: List[str] = []
        cursor = 0

        for raw_key in keys_text.split(","):
            raw_start = cursor
            raw_end = raw_start + len(raw_key)
            key = raw_key.strip()
            if not key:
                cursor = raw_end + 1
                continue

            span_start = keys_start + raw_start + (len(raw_key) - len(raw_key.lstrip()))
            span_end = keys_start + raw_start + len(raw_key.rstrip())
            if key in allowed:
                replacement_keys.append(key)
            else:
                replacement_keys.append(f"?MISSING:{key}?")
                invalid.append(
                    {
                        "original_key": key,
                        "span_start": span_start,
                        "span_end": span_end,
                        "command": command,
                        "reason": "not_in_allowed_keys",
                    }
                )
            cursor = raw_end + 1

        return f"{command}" + "{" + ",".join(replacement_keys) + "}"

    return _CITE_COMMAND_RE.sub(replace_match, text or ""), invalid


def normalize_filter_mode(mode: Optional[str]) -> str:
    """Return a supported citation filter mode."""
    normalized = (mode or "strict").strip().lower()
    if normalized not in _VALID_FILTER_MODES:
        logger.warning("Invalid CITATION_FILTER_MODE=%s; falling back to strict", mode)
        return "strict"
    return normalized


def apply_citation_filter_mode(
    text: str,
    allowed_keys: Set[str],
    mode: Optional[str],
) -> Tuple[str, List[dict]]:
    """Apply off/warn/strict behavior around filter_response."""
    normalized = normalize_filter_mode(mode)
    if normalized == "off":
        return text, []
    filtered_text, invalid = filter_response(text, allowed_keys)
    if normalized == "warn":
        return text, invalid
    return filtered_text, invalid


def build_allowed_citation_keys(
    db: Session,
    *,
    project_id: Optional[Any] = None,
    paper_id: Optional[Any] = None,
    owner_id: Optional[Any] = None,
) -> Set[str]:
    """Build the set of valid citation keys for a request's project/paper context."""
    from app.models import PaperReference, Project, ProjectReference, Reference, ResearchPaper

    references_by_id: dict[Any, Any] = {}

    project = None
    if project_id:
        project = _resolve_project(db, project_id, Project)
        if project:
            project_refs = (
                db.query(Reference)
                .join(ProjectReference, ProjectReference.reference_id == Reference.id)
                .filter(ProjectReference.project_id == project.id)
                .all()
            )
            for ref in project_refs:
                references_by_id[ref.id] = ref

    paper = None
    if paper_id:
        paper = _resolve_paper(db, paper_id, ResearchPaper, project_id=getattr(project, "id", None))
        paper_uuid = getattr(paper, "id", None)
        if not project_id:
            paper_uuid = paper_uuid or _coerce_uuid(paper_id)
        if paper_uuid:
            paper_refs = (
                db.query(Reference)
                .join(PaperReference, PaperReference.reference_id == Reference.id)
                .filter(PaperReference.paper_id == paper_uuid)
                .all()
            )
            direct_refs = db.query(Reference).filter(Reference.paper_id == paper_uuid).all()
            for ref in [*paper_refs, *direct_refs]:
                references_by_id[ref.id] = ref

    if not project_id and not paper_id and owner_id:
        owner_refs = db.query(Reference).filter(Reference.owner_id == owner_id).all()
        for ref in owner_refs:
            references_by_id[ref.id] = ref

    allowed: Set[str] = set()
    for ref in references_by_id.values():
        key = make_bib_key(
            {
                "title": getattr(ref, "title", None),
                "authors": getattr(ref, "authors", None),
                "year": getattr(ref, "year", None),
            }
        )
        if key:
            allowed.add(key)
    return allowed


def _coerce_uuid(value: Any) -> Optional[UUID]:
    try:
        return UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _parse_short_id(value: Any) -> Optional[str]:
    text = str(value or "")
    if not text or _coerce_uuid(text):
        return None
    if len(text) == 8 and text.isalnum():
        return text
    last_hyphen = text.rfind("-")
    if last_hyphen > 0:
        candidate = text[last_hyphen + 1 :]
        if len(candidate) == 8 and candidate.isalnum():
            return candidate
    return None


def _resolve_project(db: Session, project_id: Any, project_model: Any) -> Optional[Any]:
    project_uuid = _coerce_uuid(project_id)
    if project_uuid:
        return db.query(project_model).filter(project_model.id == project_uuid).first()
    short_id = _parse_short_id(project_id)
    if short_id:
        return db.query(project_model).filter(project_model.short_id == short_id).first()
    return None


def _resolve_paper(
    db: Session,
    paper_id: Any,
    paper_model: Any,
    *,
    project_id: Optional[Any] = None,
) -> Optional[Any]:
    paper_uuid = _coerce_uuid(paper_id)
    query = db.query(paper_model)
    if paper_uuid:
        if project_id:
            query = query.filter(paper_model.project_id == project_id)
        return query.filter(paper_model.id == paper_uuid).first()

    short_id = _parse_short_id(paper_id)
    if short_id:
        query = query.filter(paper_model.short_id == short_id)
        if project_id:
            query = query.filter(paper_model.project_id == project_id)
        return query.first()
    return None
