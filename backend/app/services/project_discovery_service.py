"""Service layer for orchestrating project discovery runs and persistence."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from urllib.parse import urlparse, parse_qs
import time
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Project,
    ProjectReference,
    ProjectDiscoveryRun,
    ProjectDiscoveryResult as ProjectDiscoveryResultModel,
    ProjectDiscoveryRunType,
    ProjectDiscoveryRunStatus,
    ProjectDiscoveryResultStatus,
    Reference,
    ResearchPaper,
    User,
)
from app.schemas.project import ProjectDiscoveryPreferences, ProjectDiscoveryPreferencesUpdate
from app.services.paper_discovery.models import PaperSource
from app.services.paper_discovery_service import DiscoveredPaper, DiscoveryResult, PaperDiscoveryService, SourceStats

logger = logging.getLogger(__name__)


OPENALEX_PDF_BLOCKLIST = (
    'nature.com',
    'www.nature.com',
    'rdcu.be',
    'doi.org',
    'cell.com',
    'www.cell.com',
    'linkinghub.elsevier.com',
    'sciencedirect.com',
    'www.sciencedirect.com',
)


def _is_blocked_openalex_pdf(source: str, url: Optional[str]) -> bool:
    if not url or source != PaperSource.OPENALEX.value:
        return False
    try:
        host = urlparse(url).netloc.lower()
    except Exception:
        return True
    return any(host == blocked or host.endswith(blocked) for blocked in OPENALEX_PDF_BLOCKLIST)


@dataclass
class ProjectDiscoveryOutcome:
    """Aggregate counts produced by a discovery run."""

    run_id: Optional[UUID] = None
    total_found: int = 0
    results_created: int = 0
    references_created: int = 0
    project_suggestions_created: int = 0
    source_stats: Optional[List[SourceStats]] = None


_AUTO_QUERY_SYSTEM = (
    "You are an academic search query generator. "
    "Given context about a research project, generate exactly ONE focused "
    "search query targeting a specific facet or angle of the project.\n\n"
    "Return ONLY compact single-line JSON, no markdown:\n"
    '{"query":"your search query here"}\n\n'
    "Guidelines:\n"
    "- The query should be 4-8 words, suitable for academic search APIs\n"
    "- Use precise technical terminology from the project context\n"
    "- Pick ONE specific angle (methodology, application, theory, subfield)\n"
    "- If reference titles reveal specific subfields, target one of them\n"
    "- If promoted discoveries show user interests, lean into those\n"
    "- Don't just repeat the project title — synthesize a better search angle\n"
    "- IMPORTANT: If previous queries are listed, generate something DIFFERENT\n"
    "Examples:\n"
    '- Project "ML Healthcare" with cardiac refs → {"query":"deep learning ECG signal classification"}\n'
    '- Project "NLP Arabic" with BERT refs → {"query":"Arabic language BERT pre-training"}\n'
)


def _build_auto_query_context(project: Project, db: Session) -> str:
    """Gather project context for auto-query generation. Returns a text block."""
    parts: List[str] = []
    parts.append(f"Project title: {project.title}")
    if project.idea:
        parts.append(f"Research idea: {project.idea}")
    if project.scope:
        parts.append(f"Scope: {project.scope}")
    if project.keywords:
        parts.append(f"Keywords: {', '.join(project.keywords[:10])}")

    ref_titles = (
        db.query(Reference.title)
        .join(ProjectReference, ProjectReference.reference_id == Reference.id)
        .filter(ProjectReference.project_id == project.id)
        .order_by(ProjectReference.created_at.desc())
        .all()
    )
    if ref_titles:
        titles = [r[0] for r in ref_titles if r[0]]
        if titles:
            parts.append(f"Library references ({len(titles)}): {'; '.join(titles)}")

    paper_titles = (
        db.query(ResearchPaper.title)
        .filter(ResearchPaper.project_id == project.id)
        .all()
    )
    if paper_titles:
        titles = [r[0] for r in paper_titles if r[0]]
        if titles:
            parts.append(f"Papers being written: {'; '.join(titles)}")

    # Recently promoted discovery results signal what the user found valuable
    promoted_titles = (
        db.query(ProjectDiscoveryResultModel.title)
        .filter(
            ProjectDiscoveryResultModel.project_id == project.id,
            ProjectDiscoveryResultModel.status == ProjectDiscoveryResultStatus.PROMOTED,
        )
        .order_by(ProjectDiscoveryResultModel.created_at.desc())
        .all()
    )
    if promoted_titles:
        titles = [r[0] for r in promoted_titles if r[0]]
        if titles:
            parts.append(f"Previously promoted discoveries: {'; '.join(titles)}")

    return "\n".join(parts)


_MAX_RECENT_QUERIES = 12


async def generate_auto_query(project: Project, db: Session) -> str:
    """Generate a single search query from project context using LLM.

    Each call produces a different query by including recent query history
    as exclusions. The LLM is forced to explore new angles each run.
    Falls back to project title on failure.
    """
    context = _build_auto_query_context(project, db)
    prefs = project.discovery_preferences or {}
    recent_queries: List[str] = prefs.get("recent_auto_queries", [])

    # Include recent queries in hash so cache invalidates each run
    hash_input = context + "\n" + json.dumps(recent_queries)
    context_hash = hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    # Cache: same context + same history = same query (prevents duplicate runs)
    if prefs.get("auto_query_hash") == context_hash and prefs.get("auto_query"):
        logger.debug("[AutoQuery] Cache hit for project '%s'", project.title)
        return prefs["auto_query"]

    # Context is just the title — no enrichment, skip LLM
    if "\n" not in context:
        return project.title or ""

    # Build user message with query history exclusions
    user_msg = context
    if recent_queries:
        user_msg += (
            "\n\nPreviously used queries (do NOT repeat or paraphrase these):\n"
            + "\n".join(f"- {q}" for q in recent_queries)
        )

    try:
        from openai import AsyncOpenAI
        from app.core.config import settings

        api_key = settings.OPENROUTER_API_KEY
        if not api_key:
            return project.title or ""

        client = AsyncOpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub",
            },
        )

        last_exc = None
        for attempt in range(2):
            try:
                resp = await asyncio.wait_for(
                    client.chat.completions.create(
                        model="openai/gpt-5-mini",
                        messages=[
                            {"role": "system", "content": _AUTO_QUERY_SYSTEM},
                            {"role": "user", "content": user_msg},
                        ],
                        max_completion_tokens=4096,
                        temperature=0.5,
                        extra_body={"reasoning": {"effort": "minimal"}},
                    ),
                    timeout=15.0,
                )
                raw = (resp.choices[0].message.content or "").strip()
                if raw:
                    break
                logger.warning("[AutoQuery] Empty response (attempt %d)", attempt + 1)
            except (asyncio.TimeoutError, Exception) as exc:
                last_exc = exc
                logger.warning("[AutoQuery] Attempt %d failed: %s", attempt + 1, exc)
                continue
        else:
            if last_exc:
                raise last_exc
            return project.title or ""

        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:-1] if lines[-1].startswith("```") else lines[1:])

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r'\{[^{}]*\}', raw)
            if match:
                data = json.loads(match.group())
            else:
                logger.warning("[AutoQuery] Unparseable LLM response: %s", raw[:200])
                raise

        generated = (data.get("query") or "").strip()
        if not generated and isinstance(data.get("queries"), list) and data["queries"]:
            generated = str(data["queries"][0]).strip()

        if generated:
            # Update recent query history (rolling window of 12)
            updated_recent = list(recent_queries)
            updated_recent.append(generated)
            if len(updated_recent) > _MAX_RECENT_QUERIES:
                updated_recent = updated_recent[-_MAX_RECENT_QUERIES:]

            # Store in discovery_preferences
            updated = dict(prefs)
            updated["auto_query"] = generated
            updated["auto_queries"] = updated_recent  # frontend reads this for display
            updated["auto_query_hash"] = context_hash
            updated["recent_auto_queries"] = updated_recent
            project.discovery_preferences = updated
            db.flush()
            logger.info(
                "[AutoQuery] project='%s' → query='%s' (history: %d)",
                project.title, generated, len(updated_recent),
            )
            return generated

        return project.title or ""

    except Exception as exc:
        logger.warning("[AutoQuery] Failed for project '%s': %s", project.title, exc)
        return project.title or ""


class ProjectDiscoveryManager:
    """Discover related papers for a project and enqueue them as suggestions."""

    DEFAULT_SOURCES = ['semantic_scholar', 'arxiv', 'crossref', 'openalex', 'pubmed', 'sciencedirect', 'core', 'europe_pmc']

    def __init__(self, db: Session):
        self.db = db
        self._last_run_id: Optional[UUID] = None

    async def _discover_async(
        self,
        query: str,
        sources: List[str],
        target_keywords: Optional[List[str]],
        max_results: int,
        *,
        fast_mode: bool = False,
        progress_callback: Optional[Callable[..., Any]] = None,
    ) -> DiscoveryResult:
        """Execute the async discovery search across upstream providers."""
        async with PaperDiscoveryService() as service:
            return await service.discover_papers(
                query=query,
                sources=sources,
                max_results=max_results,
                target_keywords=target_keywords,
                fast_mode=fast_mode,
                progress_callback=progress_callback,
            )

    def _run_async(self, coro):
        """Run the provided coroutine, handling nested event loops for sync contexts."""
        try:
            return asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                return loop.run_until_complete(coro)
            finally:
                asyncio.set_event_loop(None)
                loop.close()

    @property
    def last_run_id(self) -> Optional[UUID]:
        """Return the identifier of the most recent discovery run."""
        return self._last_run_id

    def discover(
        self,
        project: Project,
        user: User,
        preferences: ProjectDiscoveryPreferences,
        *,
        override_query: Optional[str] = None,
        max_results: int = 20,
        run_type: ProjectDiscoveryRunType = ProjectDiscoveryRunType.MANUAL,
    ) -> ProjectDiscoveryOutcome:
        """Perform a discovery run and persist the resulting artifacts (sync wrapper)."""
        return self._run_async(self.discover_async(
            project, user, preferences,
            override_query=override_query,
            max_results=max_results,
            run_type=run_type,
        ))

    async def discover_async(  # pylint: disable=too-many-arguments,too-many-locals,too-many-statements
        self,
        project: Project,
        user: User,
        preferences: ProjectDiscoveryPreferences,
        *,
        override_query: Optional[str] = None,
        max_results: int = 20,
        run_type: ProjectDiscoveryRunType = ProjectDiscoveryRunType.MANUAL,
        progress_callback: Optional[Callable[..., Any]] = None,
    ) -> ProjectDiscoveryOutcome:
        """Perform a discovery run and persist the resulting artifacts."""
        # Rolling window: trim oldest pending auto results to keep feed fresh
        if run_type != ProjectDiscoveryRunType.MANUAL:
            _MAX_PENDING_AUTO = 100
            auto_pending_ids = [
                row[0]
                for row in (
                    self.db.query(ProjectDiscoveryResultModel.id)
                    .join(ProjectDiscoveryRun, ProjectDiscoveryResultModel.run_id == ProjectDiscoveryRun.id)
                    .filter(
                        ProjectDiscoveryResultModel.project_id == project.id,
                        ProjectDiscoveryResultModel.status == ProjectDiscoveryResultStatus.PENDING,
                        ProjectDiscoveryRun.run_type != ProjectDiscoveryRunType.MANUAL,
                    )
                    .order_by(ProjectDiscoveryResultModel.relevance_score.desc().nullslast(), ProjectDiscoveryResultModel.created_at.desc())
                    .all()
                )
            ]
            if len(auto_pending_ids) >= _MAX_PENDING_AUTO:
                # Keep the 80 most recent, trim the rest to make room
                trim_ids = auto_pending_ids[80:]
                self.db.query(ProjectDiscoveryResultModel).filter(
                    ProjectDiscoveryResultModel.id.in_(trim_ids),
                ).delete(synchronize_session=False)
                logger.info(
                    "Trimmed %d oldest pending auto results for project %s",
                    len(trim_ids), project.id,
                )
                self.db.flush()
                # Store trim count so the frontend can show a notification
                prefs = dict(project.discovery_preferences or {})
                prefs["auto_trimmed_count"] = len(trim_ids)
                project.discovery_preferences = prefs
                self.db.flush()

            # Housekeeping: purge dismissed results older than 30 days
            from datetime import timedelta
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            stale_dismissed = (
                self.db.query(ProjectDiscoveryResultModel)
                .filter(
                    ProjectDiscoveryResultModel.project_id == project.id,
                    ProjectDiscoveryResultModel.status == ProjectDiscoveryResultStatus.DISMISSED,
                    ProjectDiscoveryResultModel.dismissed_at < cutoff,
                )
                .delete(synchronize_session=False)
            )
            if stale_dismissed:
                logger.info("Purged %d dismissed results older than 30 days for project %s", stale_dismissed, project.id)
                self.db.flush()

        query = (override_query or preferences.query or '').strip()
        if not query and run_type != ProjectDiscoveryRunType.MANUAL:
            # Auto-discovery: generate intelligent query from project context
            query = await generate_auto_query(project, self.db)
        if not query:
            query = (project.title or '').strip()
        if not query:
            raise ValueError("Discovery query cannot be empty")

        # Auto runs use fewer results per run (accumulates over time)
        if run_type != ProjectDiscoveryRunType.MANUAL:
            max_results = min(max_results, 8)

        sources = preferences.sources or self.DEFAULT_SOURCES
        keywords = preferences.keywords or project.keywords or []
        max_results = max(1, preferences.max_results or max_results)
        relevance_threshold = getattr(preferences, 'relevance_threshold', None)

        logger.info(
            "Running project discovery",
            extra={
                'project_id': str(project.id),
                'query': query,
                'sources': sources,
                'keywords': keywords,
                'max_results': max_results,
                'relevance_threshold': relevance_threshold,
            },
        )

        started_at = datetime.now(timezone.utc)
        run = ProjectDiscoveryRun(
            project_id=project.id,
            run_type=run_type,
            status=ProjectDiscoveryRunStatus.RUNNING,
            triggered_by=user.id if run_type == ProjectDiscoveryRunType.MANUAL else None,
            query=query or None,
            keywords=keywords or None,
            sources=sources or None,
            max_results=max_results,
            relevance_threshold=getattr(preferences, 'relevance_threshold', None),
            settings_snapshot=preferences.model_dump(mode="json", exclude_none=True),
            started_at=started_at,
        )
        self.db.add(run)
        self.db.flush()
        self._last_run_id = run.id

        # For manual discovery, clear previous non-promoted MANUAL results to start fresh
        if run_type == ProjectDiscoveryRunType.MANUAL:
            manual_run_ids = (
                self.db.query(ProjectDiscoveryRun.id)
                .filter(
                    ProjectDiscoveryRun.project_id == project.id,
                    ProjectDiscoveryRun.run_type == ProjectDiscoveryRunType.MANUAL,
                )
                .subquery()
            )
            deleted_count = (
                self.db.query(ProjectDiscoveryResultModel)
                .filter(
                    ProjectDiscoveryResultModel.project_id == project.id,
                    ProjectDiscoveryResultModel.status != ProjectDiscoveryResultStatus.PROMOTED,
                    ProjectDiscoveryResultModel.run_id.in_(manual_run_ids),
                )
                .delete(synchronize_session='fetch')
            )
            if deleted_count > 0:
                logger.info(f"Cleared {deleted_count} previous discovery results for project {project.id}")
            self.db.flush()

        outcome = ProjectDiscoveryOutcome(run_id=run.id)
        start_time = time.perf_counter()

        include_unpromoted = run_type != ProjectDiscoveryRunType.MANUAL
        existing_fingerprints = self._collect_existing_fingerprints(
            project,
            include_unpromoted=include_unpromoted,
        )

        try:
            fast_mode = run_type == ProjectDiscoveryRunType.MANUAL
            max_fetch_cap = max(5, min(100, max_results * 4))
            aggregated_results: List[DiscoveredPaper] = []
            service_fingerprints: Set[str] = set()
            last_source_stats: Optional[List[SourceStats]] = None

            fetch_cap = max_results
            max_attempts = 2 if fast_mode else 3
            novel_estimate = 0
            attempts = 0

            while attempts < max_attempts and novel_estimate < max_results:
                discovery_result: DiscoveryResult = await self._discover_async(
                    query=query,
                    sources=sources,
                    target_keywords=keywords,
                    max_results=fetch_cap,
                    fast_mode=fast_mode,
                    progress_callback=progress_callback,
                )

                discovered_batch = discovery_result.papers
                last_source_stats = discovery_result.source_stats

                if not discovered_batch:
                    break

                batch_added = 0
                for paper in discovered_batch:
                    fingerprint = self._fingerprint_for_paper(paper)
                    if fingerprint in service_fingerprints:
                        continue
                    service_fingerprints.add(fingerprint)
                    aggregated_results.append(paper)
                    batch_added += 1
                    if fingerprint not in existing_fingerprints:
                        novel_estimate += 1

                if novel_estimate >= max_results or batch_added == 0 or len(discovered_batch) < fetch_cap:
                    break

                attempts += 1
                if fetch_cap >= max_fetch_cap:
                    break
                fetch_cap = min(fetch_cap + max(max_results, 5), max_fetch_cap)

            logger.info(
                "Discovery query complete: query='%s', novel=%d",
                query, novel_estimate,
            )

            # Store source stats in outcome
            outcome.source_stats = last_source_stats

            # Respect max_results for newly suggested papers while retaining existing matches for status updates
            filtered_results: List[DiscoveredPaper] = []
            novel_kept = 0
            for paper in aggregated_results:
                fingerprint = self._fingerprint_for_paper(paper)
                if fingerprint not in existing_fingerprints:
                    if novel_kept >= max_results:
                        continue
                    novel_kept += 1
                filtered_results.append(paper)

            discovered = filtered_results
            # Apply relevance threshold filter (default 0.1 to remove confirmed-irrelevant noise)
            effective_threshold = relevance_threshold if relevance_threshold is not None else 0.1
            if effective_threshold > 0:
                original_count = len(discovered)
                discovered = [
                    paper for paper in discovered
                    if paper.relevance_score >= effective_threshold
                ]
                filtered_count = original_count - len(discovered)
                logger.info(
                    "Applied relevance threshold %s: filtered %s papers, %s remaining",
                    effective_threshold,
                    filtered_count,
                    len(discovered)
                )

            outcome.total_found = len(discovered)
            logger.info(
                "Discovery complete",
                extra={
                    'project_id': str(project.id),
                    'sources': sources,
                    'results': outcome.total_found,
                    'elapsed_seconds': round(time.perf_counter() - start_time, 2),
                },
            )
        except Exception as exc:  # pragma: no cover - network failures
            logger.exception("Discovery service failed: %s", exc)
            run.status = ProjectDiscoveryRunStatus.FAILED
            run.error = str(exc)
            run.completed_at = datetime.now(timezone.utc)
            self.db.commit()
            raise

        # Emit saving phase via callback
        if progress_callback is not None:
            try:
                _result = progress_callback({"type": "phase", "phase": "saving", "message": "Saving results..."})
                if asyncio.iscoroutine(_result):
                    await _result
            except Exception:
                pass

        process_start = time.perf_counter()

        for paper in discovered:
            fingerprint = self._fingerprint_for_paper(paper)

            existing_result = (
                self.db.query(ProjectDiscoveryResultModel)
                .filter(
                    ProjectDiscoveryResultModel.project_id == project.id,
                    ProjectDiscoveryResultModel.fingerprint == fingerprint,
                )
                .one_or_none()
            )

            if existing_result and existing_result.status in (
                ProjectDiscoveryResultStatus.PROMOTED,
                ProjectDiscoveryResultStatus.DISMISSED,
            ):
                existing_fingerprints.add(fingerprint)
                continue

            reference, created = self._get_or_create_reference(paper, user)
            if reference is None:
                continue
            if created:
                outcome.references_created += 1

            normalized_pdf = self._normalize_pdf_url(paper.pdf_url, paper.url)
            paper.pdf_url = normalized_pdf

            payload: Dict[str, object] = dict(paper.raw_data or {})
            payload['is_open_access'] = bool(paper.is_open_access)
            payload['has_pdf'] = bool(normalized_pdf)
            if paper.open_access_url:
                payload['open_access_url'] = paper.open_access_url
            if normalized_pdf:
                payload['pdf_url'] = normalized_pdf
            if paper.url and 'source_url' not in payload:
                payload['source_url'] = paper.url
            if paper.journal:
                payload['journal'] = paper.journal

            if existing_result:
                existing_result.run_id = run.id
                existing_result.reference_id = reference.id
                existing_result.source = paper.source
                existing_result.doi = paper.doi
                existing_result.title = paper.title
                existing_result.summary = paper.abstract
                existing_result.authors = paper.authors
                existing_result.published_year = paper.year
                existing_result.relevance_score = paper.relevance_score
                existing_result.status = ProjectDiscoveryResultStatus.PENDING
                existing_result.promoted_at = None
                existing_result.dismissed_at = None
                existing_result.payload = payload
                existing_result.updated_at = datetime.now(timezone.utc)

                existing_link = (
                    self.db.query(ProjectReference)
                    .filter(
                        ProjectReference.project_id == project.id,
                        ProjectReference.reference_id == reference.id,
                    )
                    .first()
                )
                if not existing_link:
                    outcome.project_suggestions_created += 1

                outcome.results_created += 1
                existing_fingerprints.add(fingerprint)
                continue

            if fingerprint in existing_fingerprints:
                continue

            result_row = ProjectDiscoveryResultModel(
                run_id=run.id,
                project_id=project.id,
                reference_id=reference.id,
                source=paper.source,
                doi=paper.doi,
                title=paper.title,
                summary=paper.abstract,
                authors=paper.authors,
                published_year=paper.year,
                relevance_score=paper.relevance_score,
                fingerprint=fingerprint,
                payload=payload,
            )
            self.db.add(result_row)
            outcome.results_created += 1
            existing_fingerprints.add(fingerprint)

            existing_link = (
                self.db.query(ProjectReference)
                .filter(
                    ProjectReference.project_id == project.id,
                    ProjectReference.reference_id == reference.id,
                )
                .first()
            )
            if existing_link:
                continue
            outcome.project_suggestions_created += 1

        run.status = ProjectDiscoveryRunStatus.COMPLETED
        run.completed_at = datetime.now(timezone.utc)
        self.db.commit()

        # Update stored preferences metadata
        updated_preferences = preferences.model_dump(mode="json")
        updated_preferences['last_run_at'] = datetime.now(timezone.utc).isoformat()
        updated_preferences['last_result_count'] = outcome.project_suggestions_created
        updated_preferences['last_status'] = 'ok'
        project.discovery_preferences = updated_preferences
        self.db.commit()
        self.db.refresh(project)

        if run_type == ProjectDiscoveryRunType.MANUAL and outcome.results_created > 0:
            self._purge_previous_manual_results(project.id, run.id)
            self.db.commit()
        elif run_type != ProjectDiscoveryRunType.MANUAL:
            self._prune_old_auto_runs(project.id, run.id)
            self.db.commit()

        logger.info(
            "Discovery processing complete",
            extra={
                'project_id': str(project.id),
                'references_created': outcome.references_created,
                'suggestions_created': outcome.project_suggestions_created,
                'processing_seconds': round(time.perf_counter() - process_start, 2),
                'total_seconds': round(time.perf_counter() - start_time, 2),
            },
        )

        return outcome

    def _get_or_create_reference(
        self,
        paper: DiscoveredPaper,
        user: User,
    ) -> tuple[Optional[Reference], bool]:
        """Return a reference matching the paper, creating it when needed."""
        query = self.db.query(Reference)
        reference: Optional[Reference] = None
        normalized_pdf = self._normalize_pdf_url(paper.pdf_url, paper.url)
        if _is_blocked_openalex_pdf(paper.source, normalized_pdf):
            normalized_pdf = None
        paper.pdf_url = normalized_pdf
        if normalized_pdf is None and paper.is_open_access:
            paper.is_open_access = False
        if paper.doi:
            reference = query.filter(func.lower(Reference.doi) == paper.doi.lower()).first()
        if not reference and paper.title:
            reference = (
                self.db.query(Reference)
                .filter(func.lower(Reference.title) == paper.title.lower())
                .first()
            )

        if reference:
            if paper.is_open_access and not reference.is_open_access:
                reference.is_open_access = True
            if normalized_pdf:
                if reference.pdf_url != normalized_pdf:
                    reference.pdf_url = normalized_pdf
            else:
                if reference.pdf_url:
                    parsed = urlparse(reference.pdf_url)
                    path = (parsed.path or '').lower()
                    query = (parsed.query or '').lower()
                    looks_like_pdf = path.endswith('.pdf') or '.pdf' in path or '.pdf' in query
                    if not looks_like_pdf or _is_blocked_openalex_pdf(paper.source, reference.pdf_url):
                        reference.pdf_url = None
            if not paper.is_open_access and reference.is_open_access and not reference.pdf_url:
                reference.is_open_access = False
            if _is_blocked_openalex_pdf(paper.source, reference.pdf_url):
                reference.pdf_url = None
                if reference.is_open_access and not reference.pdf_url:
                    reference.is_open_access = False
            if paper.url and not reference.url:
                reference.url = paper.url
            if paper.open_access_url and not reference.url:
                reference.url = paper.open_access_url
            return reference, False

        if not paper.title:
            return None, False

        resolved_url = paper.url or paper.open_access_url

        sanitized_pdf = normalized_pdf if not _is_blocked_openalex_pdf(paper.source, normalized_pdf) else None

        reference = Reference(
            owner_id=user.id,
            title=paper.title,
            authors=paper.authors,
            year=paper.year,
            doi=paper.doi,
            url=resolved_url,
            source=paper.source,
            journal=paper.journal,
            abstract=paper.abstract,
            relevance_score=paper.relevance_score,
            is_open_access=paper.is_open_access,
            pdf_url=sanitized_pdf,
        )
        self.db.add(reference)
        self.db.flush()
        return reference, True

    def _fingerprint_for_paper(self, paper: DiscoveredPaper) -> str:
        """Derive a deterministic fingerprint for deduplication."""
        if paper.doi:
            return f"doi:{paper.doi.strip().lower()}"
        title = (paper.title or '').strip().lower()
        if title:
            return f"title:{hashlib.sha1(title.encode('utf-8')).hexdigest()}"
        url = (paper.url or '').strip().lower()
        if url:
            return f"url:{hashlib.sha1(url.encode('utf-8')).hexdigest()}"
        return f"anon:{hashlib.sha1(str(id(paper)).encode('utf-8')).hexdigest()}"

    def _collect_existing_fingerprints(
        self,
        project: Project,
        *,
        include_unpromoted: bool = True,
    ) -> Set[str]:
        """Gather fingerprints already present for a project."""
        fingerprints: Set[str] = set()

        query = self.db.query(ProjectDiscoveryResultModel.fingerprint).filter(
            ProjectDiscoveryResultModel.project_id == project.id
        )
        if not include_unpromoted:
            query = query.filter(
                ProjectDiscoveryResultModel.status == ProjectDiscoveryResultStatus.PROMOTED
            )

        existing_results = query.all()
        fingerprints.update(row[0] for row in existing_results if row[0])

        for link in project.references:
            reference = link.reference
            if not reference:
                continue
            if reference.doi:
                fingerprints.add(f"doi:{reference.doi.strip().lower()}")
            elif reference.title:
                normalized_title = reference.title.strip().lower().encode('utf-8')
                title_hash = hashlib.sha1(normalized_title).hexdigest()
                fingerprints.add(f"title:{title_hash}")
        return fingerprints

    def _purge_previous_manual_results(self, project_id: UUID, current_run_id: UUID) -> None:
        """Remove results from earlier manual runs so fresh searches start clean."""
        manual_run_ids = [
            row[0]
            for row in (
                self.db.query(ProjectDiscoveryRun.id)
                .filter(
                    ProjectDiscoveryRun.project_id == project_id,
                    ProjectDiscoveryRun.run_type == ProjectDiscoveryRunType.MANUAL,
                    ProjectDiscoveryRun.id != current_run_id,
                )
                .all()
            )
        ]

        if not manual_run_ids:
            return

        # Remove manual run results that haven't been promoted (pending/dismissed) from prior runs
        self.db.query(ProjectDiscoveryResultModel).filter(
            ProjectDiscoveryResultModel.project_id == project_id,
            ProjectDiscoveryResultModel.run_id.in_(manual_run_ids),
            ProjectDiscoveryResultModel.status != ProjectDiscoveryResultStatus.PROMOTED,
        ).delete(synchronize_session=False)

        # Delete the historical run records to keep storage tidy
        self.db.query(ProjectDiscoveryRun).filter(
            ProjectDiscoveryRun.id.in_(manual_run_ids)
        ).delete(synchronize_session=False)

        self.db.flush()

    def _prune_old_auto_runs(self, project_id: UUID, _current_run_id: UUID) -> None:
        """Keep only the 10 most recent auto runs, delete older ones and their orphan results."""
        recent_ids = [
            row[0]
            for row in (
                self.db.query(ProjectDiscoveryRun.id)
                .filter(
                    ProjectDiscoveryRun.project_id == project_id,
                    ProjectDiscoveryRun.run_type != ProjectDiscoveryRunType.MANUAL,
                )
                .order_by(ProjectDiscoveryRun.started_at.desc())
                .limit(10)
                .all()
            )
        ]
        old_auto_runs = (
            self.db.query(ProjectDiscoveryRun.id)
            .filter(
                ProjectDiscoveryRun.project_id == project_id,
                ProjectDiscoveryRun.run_type != ProjectDiscoveryRunType.MANUAL,
                ProjectDiscoveryRun.id.notin_(recent_ids) if recent_ids else True,
            )
            .all()
        )
        old_ids = [row[0] for row in old_auto_runs]
        if not old_ids:
            return

        # Delete orphan results (non-promoted) from old runs
        self.db.query(ProjectDiscoveryResultModel).filter(
            ProjectDiscoveryResultModel.run_id.in_(old_ids),
            ProjectDiscoveryResultModel.status != ProjectDiscoveryResultStatus.PROMOTED,
        ).delete(synchronize_session=False)

        # Delete the old run records
        self.db.query(ProjectDiscoveryRun).filter(
            ProjectDiscoveryRun.id.in_(old_ids)
        ).delete(synchronize_session=False)

        if old_ids:
            logger.info("Pruned %d old auto run records for project %s", len(old_ids), project_id)

        self.db.flush()

    @staticmethod
    def merge_preferences(
        current: Dict[str, object],
        update: ProjectDiscoveryPreferencesUpdate,
    ) -> Dict[str, object]:
        """Merge partial preference updates into persisted settings."""
        new_data = dict(current or {})
        payload = update.model_dump(exclude_unset=True)
        for key, value in payload.items():
            if value is None:
                new_data.pop(key, None)
            else:
                new_data[key] = value
        return new_data

    @staticmethod
    def as_preferences(data: Optional[Dict[str, object]]) -> ProjectDiscoveryPreferences:
        """Normalize raw preference dictionaries into the pydantic model."""
        return ProjectDiscoveryPreferences.model_validate(data or {})

    @staticmethod
    def _normalize_pdf_url(pdf_url: Optional[str], source_url: Optional[str]) -> Optional[str]:
        """Best-effort normalization to ensure we point at a real PDF when possible."""

        candidate = (pdf_url or '').strip()
        source_candidate = (source_url or '').strip()

        # Prefer explicit PDF URL when it clearly ends with .pdf
        if candidate and candidate.lower().endswith('.pdf'):
            try:
                parsed = urlparse(candidate)
                host = (parsed.netloc or '').lower()
                if host.endswith('nature.com'):
                    candidate = ''
                else:
                    return candidate
            except Exception:
                return candidate

        # Handle arXiv links (abs -> pdf)
        for url in (candidate, source_candidate):
            if not url:
                continue
            if 'arxiv.org' in url:
                if '/abs/' in url:
                    base = url.split('#')[0].split('?')[0]
                    pdf_candidate = base.replace('/abs/', '/pdf/')
                    if not pdf_candidate.lower().endswith('.pdf'):
                        pdf_candidate = f"{pdf_candidate}.pdf"
                    return pdf_candidate
                if '/pdf/' in url and not url.lower().endswith('.pdf'):
                    return f"{url}.pdf"

        # Handle OpenReview URLs (forum -> pdf)
        for url in (candidate, source_candidate):
            if not url:
                continue
            if 'openreview.net' in url:
                parsed = urlparse(url)
                query = parse_qs(parsed.query)
                forum_id = query.get('id', [None])[0]
                if forum_id:
                    return f"https://openreview.net/pdf?id={forum_id}"

        # Semantic Scholar open access PDF links usually usable as-is
        if candidate:
            return candidate

        return None
