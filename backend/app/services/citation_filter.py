"""Server-side validation for LaTeX citation keys in AI output."""

from __future__ import annotations

import logging
import re
from typing import Any, Callable, Iterable, Iterator, List, Optional, Set, Tuple, Mapping
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_LATEX_COMMAND_RE = re.compile(r"\\(?P<command>[A-Za-z]+)")
# Known limits: nested brackets, braces inside keys, and %-comments are not parsed.
_OPTIONAL_CITATION_ARGS = r"(?:\s*(?:\[[^\]]*\]|\([^)]*\)|<[^>]*>))*"
_CITATION_ARGS_RE = re.compile(
    rf"(?P<star>\*?)(?P<opts>{_OPTIONAL_CITATION_ARGS})\s*(?P<group>\{{[^{{}}]*\}})"
)
_MULTI_CITE_GROUP_RE = re.compile(
    rf"(?P<opts>{_OPTIONAL_CITATION_ARGS})\s*(?P<group>\{{[^{{}}]*\}})"
)
_BIBKEY_LIST_RE = re.compile(r"\s*[^,\s]+(?:\s*,\s*[^,\s]+)*\s*,?\s*")
_CITATION_COMMANDS = frozenset(
    {
        "autocite",
        "autocites",
        "avolcite",
        "cite",
        "citea",
        "citealp",
        "citealt",
        "citeauthor",
        "citedate",
        "citefield",
        "citename",
        "citenum",
        "citep",
        "cites",
        "citet",
        "citetalias",
        "citetitle",
        "citeurl",
        "citeyear",
        "citeyearpar",
        "footcite",
        "footcites",
        "footcitetext",
        "footfullcite",
        "ftvolcite",
        "fullcite",
        "fvolcite",
        "nocite",
        "parencite",
        "parencites",
        "pvolcite",
        "smartcite",
        "shortcite",
        "smartcites",
        "supercite",
        "supercites",
        "svolcite",
        "textcite",
        "textcites",
        "tvolcite",
        "volcite",
        "volcites",
    }
)
_MULTI_GROUP_CITATION_COMMANDS = frozenset(
    {"autocites", "cites", "footcites", "parencites", "smartcites", "supercites", "textcites", "volcites"}
)
_VOLUME_CITATION_COMMANDS = frozenset(
    {"volcite", "volcites", "pvolcite", "fvolcite", "ftvolcite", "svolcite", "tvolcite", "avolcite"}
)
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


def generate_citation_key(paper: dict, used_keys: Optional[Set[str]] = None) -> str:
    """Generate a normalized key and, when requested, allocate a unique suffix."""
    authors = paper.get("authors") or []
    if isinstance(authors, str):
        authors = [author.strip() for author in authors.split(",") if author.strip()]
    base = make_bib_key({**paper, "authors": authors})
    if used_keys is None:
        return base
    key = base
    suffix = 0
    while key in used_keys:
        key = base + (chr(ord("a") + suffix) if suffix < 26 else str(suffix - 24))
        suffix += 1
    used_keys.add(key)
    return key


def citation_identity(paper: dict) -> Tuple[str, str, str]:
    """Identify matching search/library metadata without depending on DB order."""
    authors = paper.get("authors") or []
    if isinstance(authors, str):
        authors = [author.strip() for author in authors.split(",") if author.strip()]
    return (
        " ".join((paper.get("title") or "").lower().split()),
        ",".join(" ".join(str(author).lower().split()) for author in authors),
        str(paper.get("year") or ""),
    )


def build_citation_key_map(
    papers: Iterable[dict], extra_papers: Iterable[dict] = (),
    *, ordering_key: Optional[Callable[[dict], Any]] = None,
) -> dict[str, dict]:
    """Assign deterministic keys to a complete citation scope, deduplicating copies.

    Select subsets only after building this map so a paper retains its suffix.
    Collision members follow input insertion order unless ordering_key is given;
    use creation order so an existing paper's key never changes when another
    paper is added. Allocate sequentially, including when a later paper's native
    base matches a suffix already assigned to an earlier paper.
    """
    unique = {
        (*citation_identity(paper), str(paper.get("_reference_id") or "")): paper
        for paper in papers
    }
    library_identities = {citation_identity(paper) for paper in unique.values()}
    used_keys: Set[str] = set()
    result: dict[str, dict] = {}
    ordered_papers = list(unique.values())
    if ordering_key is not None:
        ordered_papers.sort(key=ordering_key)
    for paper in ordered_papers:
        result[generate_citation_key(paper, used_keys)] = paper
    # Search results may extend a library scope, but must not rename its keys.
    ordered_extras = list({citation_identity(paper): paper for paper in extra_papers}.values())
    if ordering_key is not None:
        ordered_extras.sort(key=ordering_key)
    for paper in ordered_extras:
        identity = citation_identity(paper)
        if identity not in library_identities:
            result[generate_citation_key(paper, used_keys)] = paper
    return result


def scope_entry_time(entered_at: Mapping[Any, Any], ref: Any) -> Any:
    """When ``ref`` entered the scope being keyed, or None if it is not a member.

    A member whose link row carries no timestamp keeps its membership and is
    ordered by its own created_at instead of being demoted behind the others.
    """
    if ref.id not in entered_at:
        return None
    return entered_at[ref.id] or getattr(ref, "created_at", None)


def _reference_paper_order(paper: dict) -> tuple:
    """Order library records by entry into the scope, then ID; keep ID-less input order.

    ``scope_entered_at`` is when the reference was linked into the project or
    paper being keyed. It wins over the row's own ``created_at`` because
    Reference rows are shared across projects, so an older row can enter a
    project later. An existing paper's key never changes when another paper
    is added after it. Library members allocate before references that belong
    only to a paper, so a library reference has the same key on the project
    pages and inside every paper of that project, whatever the paper-only
    references' own timestamps are.
    """
    reference_id = paper.get("_reference_id")
    if reference_id is None:
        return (True,)
    scope_entered_at = paper.get("scope_entered_at")
    entered_at = scope_entered_at or paper.get("created_at")
    return (False, scope_entered_at is None, entered_at is None, entered_at, str(reference_id))


def build_citation_lookup(
    papers: Iterable[dict], extra_papers: Iterable[dict] = (),
) -> dict[str, dict]:
    """Resolve the canonical key for every paper in a citation scope.

    Exactly the keys the allocator assigns and nothing else: the allowed set
    used by the citation filter is derived from this map, so any extra alias
    here would let the model cite a key that no exporter produces.
    """
    return build_citation_key_map(list(papers), extra_papers, ordering_key=_reference_paper_order)


def reference_citation_keys(
    references: Iterable[Any], *, entered_at: Optional[Mapping[Any, Any]] = None,
) -> dict[Any, str]:
    """Return reference ID to key using the same collection algorithm as AI tools.

    ``entered_at`` maps a reference id to when it entered the scope being keyed
    (see ``project_reference_entry_times``). Without it, ordering falls back to
    the row's own created_at, which is right for paper-scoped references.
    """
    entered_at = entered_at or {}
    papers = [
        {
            "_reference_id": ref.id, "title": ref.title,
            "authors": ref.authors, "year": ref.year,
            "created_at": getattr(ref, "created_at", None),
            "scope_entered_at": scope_entry_time(entered_at, ref),
        }
        for ref in references
    ]
    return {
        paper["_reference_id"]: key
        for key, paper in build_citation_key_map(papers, ordering_key=_reference_paper_order).items()
    }


def extract_cite_keys(text: str) -> List[Tuple[str, int, int, str]]:
    """Return (key, span_start, span_end, command) for supported citation commands."""
    results: List[Tuple[str, int, int, str]] = []
    source = text or ""
    for match, command, normalized_command in _iter_citation_groups(source):
        group = match.group("group")
        keys_text = group[1:-1]
        keys_start = match.start("group") + 1
        cursor = 0
        for raw_key in keys_text.split(","):
            raw_start = cursor
            raw_end = raw_start + len(raw_key)
            key = raw_key.strip()
            if key and not (normalized_command == "nocite" and key == "*"):
                span_start = keys_start + raw_start + (len(raw_key) - len(raw_key.lstrip()))
                span_end = keys_start + raw_start + len(raw_key.rstrip())
                results.append((key, span_start, span_end, command))
            cursor = raw_end + 1
    return sorted(results, key=lambda item: item[1])


def filter_response(text: str, allowed_keys: Set[str]) -> Tuple[str, List[dict]]:
    """Replace every citation key not present in allowed_keys with a missing marker."""
    invalid: List[dict] = []
    allowed = set(allowed_keys or set())
    source = text or ""
    replacements: List[Tuple[int, int, str]] = []

    for match, command, normalized_command in _iter_citation_groups(source):
        group = match.group("group")
        keys_text = group[1:-1]
        keys_start = match.start("group") + 1
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
            if key in allowed or (normalized_command == "nocite" and key == "*"):
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

        replacements.append((keys_start, match.end("group") - 1, ",".join(replacement_keys)))

    # Key-group spans are absolute and non-overlapping: nested citations live
    # in optional arguments, outside the outer key group. The scanner yields
    # the outer group first, so sort by position before splicing right to left.
    replacements.sort(key=lambda item: item[0])
    invalid.sort(key=lambda item: item["span_start"])
    filtered = source
    for span_start, span_end, replacement in reversed(replacements):
        filtered = filtered[:span_start] + replacement + filtered[span_end:]

    return filtered, invalid


def _iter_citation_groups(text: str) -> Iterator[Tuple[re.Match[str], str, str]]:
    """Yield key groups while scanning only command names, including nested ones."""
    # finditer resumes at the end of each command NAME, never its arguments,
    # so citations inside wrappers or citation notes are still discovered.
    for command_match in _LATEX_COMMAND_RE.finditer(text):
        normalized_command = command_match.group("command").lower()
        if normalized_command not in _CITATION_COMMANDS:
            continue

        args_match = _CITATION_ARGS_RE.match(text, command_match.end())
        if args_match is None:
            continue

        command = "\\" + command_match.group("command") + args_match.group("star")
        if normalized_command in {"citefield", "citename"}:
            # The first brace group is the key; the next is a field/name selector.
            yield args_match, command, normalized_command
            continue
        if normalized_command in _VOLUME_CITATION_COMMANDS:
            # These commands take [prenote]{volume}[postnote]{key}; only the
            # final key group is validated, preserving the volume and notes.
            args_match = _MULTI_CITE_GROUP_RE.match(text, args_match.end())
            if args_match is None:
                continue
        yield args_match, command, normalized_command

        if normalized_command not in _MULTI_GROUP_CITATION_COMMANDS:
            continue

        group_end = args_match.end()
        while next_group := _MULTI_CITE_GROUP_RE.match(text, group_end):
            if normalized_command in _VOLUME_CITATION_COMMANDS:
                # Each continuation repeats {volume}[postnote]{key}.
                next_group = _MULTI_CITE_GROUP_RE.match(text, next_group.end())
                if next_group is None:
                    break
            keys_text = next_group.group("group")[1:-1]
            if not _BIBKEY_LIST_RE.fullmatch(keys_text):
                break
            yield next_group, command, normalized_command
            group_end = next_group.end()


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


def project_reference_entry_times(db: Session, project_id: Any) -> dict[Any, Any]:
    """Map reference id to when it was linked into the project (ProjectReference.created_at)."""
    from app.models import ProjectReference

    rows = (
        db.query(ProjectReference.reference_id, ProjectReference.created_at)
        .filter(ProjectReference.project_id == project_id)
        .all()
    )
    return {reference_id: created_at for reference_id, created_at in rows}


def build_allowed_citation_keys(
    db: Session,
    *,
    project_id: Optional[Any] = None,
    paper_id: Optional[Any] = None,
    owner_id: Optional[Any] = None,
) -> Set[str]:
    """Build the set of valid citation keys for a request's project/paper context."""
    return set(scope_citation_keys(db, project_id=project_id, paper_id=paper_id, owner_id=owner_id).values())


def scope_citation_keys(
    db: Session,
    *,
    project_id: Optional[Any] = None,
    paper_id: Optional[Any] = None,
    owner_id: Optional[Any] = None,
) -> dict[Any, str]:
    """Reference id -> citation key for a request's project/paper context.

    List endpoints serve these so the editor inserts exactly the key the
    filter accepts; allocate over the whole scope, never over a page.
    """
    from app.models import PaperReference, Project, ProjectReference, Reference, ResearchPaper

    references_by_id: dict[Any, Any] = {}
    entry_times: dict[Any, Any] = {}

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
            entry_times = project_reference_entry_times(db, project.id)

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

    return {
        paper["_reference_id"]: key
        for key, paper in build_citation_lookup(
            {
                "_reference_id": ref.id, "title": ref.title,
                "authors": ref.authors, "year": ref.year,
                "created_at": getattr(ref, "created_at", None),
                "scope_entered_at": scope_entry_time(entry_times, ref),
            }
            for ref in references_by_id.values()
        ).items()
    }


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
