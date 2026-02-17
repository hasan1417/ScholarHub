"""Proactive AI insight generation.

All analysis is deterministic -- no LLM calls.  The service inspects
project state (papers, references, LaTeX content, timestamps) and
returns actionable insights sorted by priority.
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import List
from uuid import UUID

from sqlalchemy.orm import Session, defer

from app.models import (
    Project,
    ProjectReference,
    ProjectReferenceStatus,
    ResearchPaper,
    Reference,
)

logger = logging.getLogger(__name__)

PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

# LaTeX \cite variants we recognise
_CITE_RE = re.compile(
    r"\\(?:cite|citep|citet|citeauthor|citeyear|parencite|textcite|autocite)\s*"
    r"(?:\[[^\]]*\])?\s*"  # optional [...] argument
    r"\{([^}]+)\}",
    re.IGNORECASE,
)

# Simple section heading detector (\section{...}, \subsection{...}, etc.)
_SECTION_RE = re.compile(r"\\(?:sub)*section\*?\{([^}]+)\}", re.IGNORECASE)


@dataclass
class ProactiveInsight:
    type: str  # new_papers | citation_gap | coverage_gap | methodology_suggestion | writing_reminder
    title: str
    message: str
    priority: str  # high | medium | low
    action_type: str  # search | navigate | dismiss
    action_data: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class ProactiveAIService:
    """Generate deterministic proactive insights for a project."""

    def __init__(self, db: Session, project_id: UUID, user_id: UUID):
        self.db = db
        self.project_id = project_id
        self.user_id = user_id

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_insights(self) -> List[ProactiveInsight]:
        # Single consolidated query for all papers, deferring heavy columns
        papers = (
            self.db.query(ResearchPaper)
            .options(defer(ResearchPaper.latex_crdt_state), defer(ResearchPaper.content_json))
            .filter(ResearchPaper.project_id == self.project_id)
            .all()
        )

        insights: list[ProactiveInsight] = []
        # NOTE: _check_citation_gaps disabled -- generates false positives because
        # synthesised authorYEAR keys almost never match real LaTeX \cite{} keys.
        try:
            insights.extend(self._check_coverage_gaps(papers))
        except Exception:
            logger.exception("coverage gap check failed")
        try:
            insights.extend(self._check_stale_library())
        except Exception:
            logger.exception("stale library check failed")
        try:
            insights.extend(self._check_writing_progress(papers))
        except Exception:
            logger.exception("writing progress check failed")
        return sorted(insights, key=lambda i: PRIORITY_ORDER.get(i.priority, 9))

    # ------------------------------------------------------------------
    # Citation gap detection
    # ------------------------------------------------------------------

    def _check_citation_gaps(self) -> List[ProactiveInsight]:
        insights: list[ProactiveInsight] = []

        papers = (
            self.db.query(ResearchPaper)
            .filter(ResearchPaper.project_id == self.project_id)
            .all()
        )

        # Collect all citation keys used in the project library
        library_keys = self._get_library_citation_keys()

        for paper in papers:
            latex = self._get_latex_source(paper)
            if not latex:
                continue

            cited_keys = self._extract_cite_keys(latex)
            if not cited_keys:
                continue

            # Keys cited in LaTeX but missing from project library
            missing = cited_keys - library_keys
            if missing:
                sample = ", ".join(sorted(missing)[:5])
                extra = f" and {len(missing) - 5} more" if len(missing) > 5 else ""
                insights.append(
                    ProactiveInsight(
                        type="citation_gap",
                        title="Unlinked citations detected",
                        message=(
                            f"Paper \"{paper.title}\" cites {len(missing)} key(s) not in your "
                            f"project library: {sample}{extra}. Consider adding the matching references."
                        ),
                        priority="high",
                        action_type="navigate",
                        action_data={"paper_id": str(paper.id), "missing_keys": sorted(missing)[:10]},
                    )
                )

        return insights

    # ------------------------------------------------------------------
    # Coverage gap detection
    # ------------------------------------------------------------------

    def _check_coverage_gaps(self, papers: List[ResearchPaper]) -> List[ProactiveInsight]:
        insights: list[ProactiveInsight] = []

        project = self.db.query(Project).filter(Project.id == self.project_id).first()
        if not project:
            return insights

        # Gather topic keywords from project keywords + paper keywords
        topic_keywords: set[str] = set()
        if project.keywords:
            for kw in project.keywords:
                cleaned = kw.lower().strip()
                if len(cleaned) >= 4:
                    topic_keywords.add(cleaned)

        for paper in papers:
            if paper.keywords:
                for kw in paper.keywords:
                    cleaned = kw.lower().strip()
                    if len(cleaned) >= 4:
                        topic_keywords.add(cleaned)

        if not topic_keywords:
            return insights

        # Count library references per topic keyword (word-boundary match on
        # title + abstract of approved references)
        refs = (
            self.db.query(Reference)
            .join(ProjectReference, ProjectReference.reference_id == Reference.id)
            .filter(
                ProjectReference.project_id == self.project_id,
                ProjectReference.status == ProjectReferenceStatus.APPROVED,
            )
            .all()
        )

        keyword_counts: dict[str, int] = {kw: 0 for kw in topic_keywords}
        for ref in refs:
            text_blob = f"{ref.title or ''} {ref.abstract or ''}".lower()
            for kw in topic_keywords:
                if re.search(rf'\b{re.escape(kw)}\b', text_blob, re.IGNORECASE):
                    keyword_counts[kw] += 1

        if not keyword_counts:
            return insights

        max_count = max(keyword_counts.values())
        if max_count < 2:
            # Not enough data to judge coverage gaps
            return insights

        for kw, count in keyword_counts.items():
            # Flag topics with significantly fewer references than the best-covered topic
            if count <= 1 and max_count >= 4:
                well_covered = max(keyword_counts, key=keyword_counts.get)  # type: ignore[arg-type]
                insights.append(
                    ProactiveInsight(
                        type="coverage_gap",
                        title="Topic coverage gap",
                        message=(
                            f"Your library has {keyword_counts[well_covered]} references on "
                            f"'{well_covered}' but only {count} on '{kw}'. "
                            f"Consider searching for more papers on '{kw}'."
                        ),
                        priority="medium",
                        action_type="search",
                        action_data={"query": kw},
                    )
                )

        return insights

    # ------------------------------------------------------------------
    # Stale library check
    # ------------------------------------------------------------------

    def _check_stale_library(self) -> List[ProactiveInsight]:
        insights: list[ProactiveInsight] = []

        latest_ref = (
            self.db.query(ProjectReference)
            .filter(
                ProjectReference.project_id == self.project_id,
                ProjectReference.status == ProjectReferenceStatus.APPROVED,
            )
            .order_by(ProjectReference.created_at.desc())
            .first()
        )

        if not latest_ref or not latest_ref.created_at:
            return insights

        age = datetime.now(timezone.utc) - latest_ref.created_at.replace(tzinfo=timezone.utc)
        if age > timedelta(days=14):
            weeks = age.days // 7
            insights.append(
                ProactiveInsight(
                    type="new_papers",
                    title="Library may be outdated",
                    message=(
                        f"Your project library hasn't been updated in {weeks} week(s). "
                        "New papers may be available in your research area."
                    ),
                    priority="low",
                    action_type="search",
                    action_data={"query": ""},
                )
            )

        return insights

    # ------------------------------------------------------------------
    # Writing progress check
    # ------------------------------------------------------------------

    def _check_writing_progress(self, papers: List[ResearchPaper]) -> List[ProactiveInsight]:
        insights: list[ProactiveInsight] = []

        now = datetime.now(timezone.utc)

        for paper in papers:
            latex = self._get_latex_source(paper)
            created = paper.created_at
            if created and created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)

            # Paper stuck in draft with no content
            if paper.status == "draft" and not latex and created:
                age_days = (now - created).days
                if age_days >= 7:
                    insights.append(
                        ProactiveInsight(
                            type="writing_reminder",
                            title="Paper awaiting content",
                            message=(
                                f"Paper \"{paper.title}\" has been in draft for {age_days} days "
                                "with no content. Ready to start writing?"
                            ),
                            priority="medium",
                            action_type="navigate",
                            action_data={"paper_id": str(paper.id)},
                        )
                    )
                continue

            # Paper has LaTeX content -- check for missing standard sections
            if latex:
                sections_found = {m.group(1).strip().lower() for m in _SECTION_RE.finditer(latex)}
                # Normalise: map common variations to canonical names
                normalised: set[str] = set()
                for s in sections_found:
                    normalised.add(s)
                    # "methods" -> "methodology"
                    if s in ("methods", "method", "approach"):
                        normalised.add("methodology")
                    if s in ("conclusion",):
                        normalised.add("conclusions")
                    if s in ("conclusions",):
                        normalised.add("conclusion")

                missing: list[str] = []
                # Only check a focused set of must-have sections
                for required in ("introduction", "conclusion", "conclusions"):
                    # conclusion or conclusions is fine
                    if required == "conclusions" and "conclusion" in normalised:
                        continue
                    if required == "conclusion" and "conclusions" in normalised:
                        continue
                    if required not in normalised:
                        missing.append(required.title())

                if missing and len(sections_found) >= 2:
                    # Only flag if the paper already has some structure
                    insights.append(
                        ProactiveInsight(
                            type="writing_reminder",
                            title="Missing paper section(s)",
                            message=(
                                f"Paper \"{paper.title}\" appears to be missing: "
                                f"{', '.join(missing)}."
                            ),
                            priority="medium",
                            action_type="navigate",
                            action_data={"paper_id": str(paper.id)},
                        )
                    )

        return insights

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_latex_source(self, paper: ResearchPaper) -> str | None:
        """Return combined LaTeX source for a paper (multi-file aware)."""
        if paper.latex_files and isinstance(paper.latex_files, dict):
            parts = list(paper.latex_files.values())
            if parts:
                return "\n".join(str(p) for p in parts if p)
        if paper.content:
            return paper.content
        return None

    def _extract_cite_keys(self, latex: str) -> set[str]:
        """Extract all citation keys from LaTeX source."""
        keys: set[str] = set()
        for match in _CITE_RE.finditer(latex):
            raw = match.group(1)
            for key in raw.split(","):
                k = key.strip()
                if k:
                    keys.add(k)
        return keys

    def _get_library_citation_keys(self) -> set[str]:
        """Build a set of plausible citation keys from the project library.

        We construct 'authorYEAR' keys from approved references so we
        can match them against \\cite{smith2024} style keys.
        """
        keys: set[str] = set()
        refs = (
            self.db.query(Reference)
            .join(ProjectReference, ProjectReference.reference_id == Reference.id)
            .filter(
                ProjectReference.project_id == self.project_id,
                ProjectReference.status == ProjectReferenceStatus.APPROVED,
            )
            .all()
        )
        for ref in refs:
            # Generate common citation key forms
            if ref.authors and ref.year:
                first_author = ref.authors[0] if ref.authors else ""
                # Extract last name (handle "First Last" and "Last, First")
                if "," in first_author:
                    last_name = first_author.split(",")[0].strip()
                else:
                    parts = first_author.strip().split()
                    last_name = parts[-1] if parts else ""
                if last_name:
                    keys.add(f"{last_name.lower()}{ref.year}")
                    keys.add(f"{last_name.lower()}{str(ref.year)[-2:]}")
            # Also include DOI as a possible key
            if ref.doi:
                keys.add(ref.doi.lower())
        return keys
