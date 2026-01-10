from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models import (
    Meeting,
    Project,
    ProjectDiscussionChannel,
    ProjectDiscussionChannelResource,
    ProjectDiscussionMessage,
    ProjectDiscussionResourceType,
    ProjectDiscussionTask,
    Reference,
    ResearchPaper,
)
from app.services.discussion_ai.types import (
    ChannelContext,
    MessageDigest,
    PaperObjectiveDigest,
    ResourceDigest,
    TaskDigest,
)


class ResourceDigestBuilder:
    """Build lightweight summaries for channel-linked resources."""

    def __init__(self, truncate: int = 320) -> None:
        self.truncate = truncate

    def build(self, resource: ProjectDiscussionChannelResource) -> ResourceDigest:
        resource_type = ProjectDiscussionResourceType(resource.resource_type)
        details = dict(resource.details or {})

        meeting_title: Optional[str] = None
        if resource_type == ProjectDiscussionResourceType.MEETING:
            meeting = getattr(resource, "meeting", None)
            meeting_title = self._meeting_title(meeting)
            if meeting_title:
                details.setdefault("title", meeting_title)
                details.setdefault("summary", meeting_title)

        title = self._normalize_title(resource_type, details, fallback=meeting_title)
        summary = details.get("summary")
        if summary:
            summary = self._truncate(summary)

        metadata: List[str] = []
        if resource_type == ProjectDiscussionResourceType.PAPER:
            if details.get("status"):
                metadata.append(str(details["status"]))
            if details.get("year"):
                metadata.append(str(details["year"]))
        elif resource_type == ProjectDiscussionResourceType.REFERENCE:
            if details.get("source"):
                metadata.append(str(details["source"]))
        elif resource_type == ProjectDiscussionResourceType.MEETING:
            if details.get("status"):
                metadata.append(str(details["status"]))
            if details.get("has_transcript"):
                metadata.append("Transcript available")

        return ResourceDigest(
            id=resource.id,
            resource_type=resource_type,
            title=title,
            summary=summary,
            metadata=tuple(metadata),
        )

    def _normalize_title(
        self,
        resource_type: ProjectDiscussionResourceType,
        details: dict,
        *,
        fallback: Optional[str] = None,
    ) -> str:
        title = details.get("title")
        if isinstance(title, str):
            cleaned = title.strip()
            placeholder_tokens = {
                "summary will appear here soon.",
                "summary will appear here soon. (preview)",
            }
            normalized = cleaned.lower()
            if normalized in placeholder_tokens or any(
                normalized.startswith(token) for token in placeholder_tokens
            ):
                cleaned = ""
            title = cleaned
        else:
            title = ""

        if not title:
            fallback_candidates = [
                details.get("name"),
                details.get("meeting_title"),
                details.get("document_title"),
            ]
            for candidate in fallback_candidates:
                if isinstance(candidate, str) and candidate.strip():
                    title = candidate.strip()
                    break

        if not title and fallback:
            title = fallback

        if not title:
            title = self._fallback_title(resource_type)

        return self._shorten_title(title)

    def _meeting_title(self, meeting) -> Optional[str]:  # type: ignore[no-untyped-def]
        if not meeting:
            return None

        summary = getattr(meeting, "summary", None)
        title = self._clean_legacy_placeholder(summary)
        if title:
            return title

        session = getattr(meeting, "session", None)
        candidates = [
            getattr(session, "ended_at", None) if session else None,
            getattr(session, "started_at", None) if session else None,
            getattr(meeting, "created_at", None),
            getattr(meeting, "updated_at", None),
        ]
        timestamp = next((dt for dt in candidates if dt is not None), None)

        if timestamp is None:
            timestamp = datetime.now(timezone.utc)
        elif timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)

        date_str = timestamp.astimezone(timezone.utc).date().isoformat()
        return f"Sync Space - {date_str}"

    @staticmethod
    def _clean_legacy_placeholder(value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        trimmed = value.strip()
        if not trimmed:
            return None
        normalized = trimmed.casefold()
        legacy_tokens = {
            "summary will appear here soon.",
            "summary will appear here soon. (preview)",
        }
        if normalized in legacy_tokens:
            return None
        return trimmed

    def _shorten_title(self, value: str, limit: int = 80) -> str:
        text = value.strip()
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    def _truncate(self, value: str) -> str:
        if len(value) <= self.truncate:
            return value
        return value[: self.truncate - 1].rstrip() + "…"

    @staticmethod
    def _fallback_title(resource_type: ProjectDiscussionResourceType) -> str:
        if resource_type == ProjectDiscussionResourceType.PAPER:
            return "Project paper"
        if resource_type == ProjectDiscussionResourceType.REFERENCE:
            return "Related paper"
        if resource_type == ProjectDiscussionResourceType.MEETING:
            return "Transcript"
        return "Resource"


class ChannelContextAssembler:
    """Collect channel-scoped context (messages, resources, tasks)."""

    def __init__(self, db: Session, *, message_limit: int = 20) -> None:
        self.db = db
        self.message_limit = message_limit
        self.resource_builder = ResourceDigestBuilder()

    def _parse_channel_scope(self, channel_scope: Optional[dict]) -> Optional[dict]:
        """Parse channel scope from JSONB to a usable dict with UUIDs."""
        if not channel_scope or not isinstance(channel_scope, dict):
            return None  # Project-wide

        result = {}
        for key in ["paper_ids", "reference_ids", "meeting_ids"]:
            ids = channel_scope.get(key)
            if ids and isinstance(ids, list):
                # Convert string UUIDs to UUID objects
                result[key] = set(UUID(str(id_val)) if not isinstance(id_val, UUID) else id_val for id_val in ids)
            else:
                result[key] = set()

        # If all sets are empty, return None (project-wide)
        if not any(result.values()):
            return None

        return result

    def build(
        self,
        project: Project,
        channel: ProjectDiscussionChannel,
        *,
        message_limit: Optional[int] = None,
        resource_scope: Optional[Sequence[ProjectDiscussionResourceType]] = None,
    ) -> ChannelContext:
        limit = message_limit or self.message_limit
        messages = self._load_messages(channel.id, limit)

        # Parse channel-level scope (specific resource IDs)
        channel_scope_ids = None
        if hasattr(channel, 'scope') and channel.scope:
            channel_scope_ids = self._parse_channel_scope(channel.scope)

        # Load channel-linked resources
        channel_resources = self._load_resources(channel, resource_scope)

        # Load project-wide resources and merge (avoiding duplicates)
        # If channel has specific scope IDs, filter by those; otherwise load all
        project_resources = self._load_project_resources(
            project.id,
            resource_scope,
            specific_ids=channel_scope_ids,
        )
        channel_resource_ids = {r.id for r in channel_resources}
        all_resources = list(channel_resources)
        for pr in project_resources:
            if pr.id not in channel_resource_ids:
                all_resources.append(pr)

        tasks = self._load_tasks(channel.id)
        project_objectives = tuple(self._parse_project_objectives(project.scope))
        paper_objectives = tuple(self._load_paper_objectives(project.id))
        scope_tuple = tuple(resource_scope) if resource_scope else tuple()

        summary = channel.description.strip() if channel.description else None

        return ChannelContext(
            project_id=project.id,
            project_title=project.title,
            channel_id=channel.id,
            channel_name=channel.name,
            channel_description=channel.description,
            summary=summary,
            messages=messages,
            resources=tuple(all_resources),
            tasks=tasks,
            project_objectives=project_objectives,
            paper_objectives=paper_objectives,
            resource_scope=scope_tuple,
        )

    def _load_messages(self, channel_id: UUID, limit: int) -> List[MessageDigest]:
        rows = (
            self.db.query(ProjectDiscussionMessage)
            .options(joinedload(ProjectDiscussionMessage.user))
            .filter(
                ProjectDiscussionMessage.channel_id == channel_id,
                ProjectDiscussionMessage.is_deleted.is_(False),
            )
            .order_by(ProjectDiscussionMessage.created_at.desc())
            .limit(limit)
            .all()
        )
        digests: List[MessageDigest] = []
        for row in reversed(rows):
            user = row.user
            if user:
                name_parts = [
                    getattr(user, "name", None),
                    getattr(user, "display_name", None),
                    " ".join(
                        part
                        for part in [
                            getattr(user, "first_name", None),
                            getattr(user, "last_name", None),
                        ]
                        if part
                    ).strip() or None,
                ]
                email_fallback = user.email.split("@")[0] if user.email else None
                author_name = next((part for part in name_parts if part), email_fallback)
            else:
                author_name = None
            author_name = author_name or "Unknown"
            digests.append(
                MessageDigest(
                    id=row.id,
                    author_name=author_name,
                    author_id=user.id if user else None,
                    content=row.content,
                    created_at=row.created_at or datetime.utcnow(),
                    parent_id=row.parent_id,
                )
            )
        return digests

    def _load_resources(
        self,
        channel: ProjectDiscussionChannel,
        resource_scope: Optional[Sequence[ProjectDiscussionResourceType]] = None,
    ) -> List[ResourceDigest]:
        if channel.resources:
            resources = channel.resources
        else:
            resources = (
                self.db.query(ProjectDiscussionChannelResource)
                .filter(ProjectDiscussionChannelResource.channel_id == channel.id)
                .order_by(ProjectDiscussionChannelResource.created_at.asc())
                .all()
            )
        allowed: Optional[set[ProjectDiscussionResourceType]] = None
        if resource_scope:
            allowed = {ProjectDiscussionResourceType(item) for item in resource_scope}
        digests = []
        for resource in resources:
            digest = self.resource_builder.build(resource)
            if allowed and digest.resource_type not in allowed:
                continue
            # Skip meeting resources without meaningful content
            # Require meaningful title OR at least 50 chars of summary/transcript
            MIN_CONTENT_LENGTH = 50
            if digest.resource_type == ProjectDiscussionResourceType.MEETING:
                has_meaningful_title = (
                    digest.title and
                    not digest.title.lower().startswith('sync space') and
                    not digest.title.lower().startswith('meeting ')
                )
                has_meaningful_content = bool(
                    digest.summary and
                    digest.summary.strip() and
                    len(digest.summary.strip()) >= MIN_CONTENT_LENGTH
                )
                if not has_meaningful_title and not has_meaningful_content:
                    continue
            digests.append(digest)
        return digests

    def _load_tasks(self, channel_id: UUID) -> List[TaskDigest]:
        tasks = (
            self.db.query(ProjectDiscussionTask)
            .filter(ProjectDiscussionTask.channel_id == channel_id)
            .order_by(ProjectDiscussionTask.created_at.asc())
            .all()
        )
        digests: List[TaskDigest] = []
        for task in tasks:
            summary = task.description.strip() if task.description else None
            digests.append(
                TaskDigest(
                    id=task.id,
                    title=task.title,
                    status=task.status,
                    summary=summary,
                    due_date=task.due_date,
                )
            )
        return digests

    def _parse_project_objectives(self, scope: Optional[str]) -> List[str]:
        if not scope:
            return []
        entries = re.split(r"\r?\n|•", scope)
        parsed: List[str] = []
        for entry in entries:
            cleaned = re.sub(r"^\s*\d+[\).\-\s]*", "", entry or "").strip()
            if cleaned:
                parsed.append(cleaned)
        return parsed

    def _load_paper_objectives(self, project_id: UUID) -> List[PaperObjectiveDigest]:
        rows = (
            self.db.query(ResearchPaper.id, ResearchPaper.title, ResearchPaper.objectives)
            .filter(ResearchPaper.project_id == project_id)
            .all()
        )
        digests: List[PaperObjectiveDigest] = []
        for paper_id, title, objectives in rows:
            parsed: List[str] = []
            if isinstance(objectives, list):
                parsed = [str(item).strip() for item in objectives if str(item).strip()]
            elif isinstance(objectives, str) and objectives.strip():
                parsed = [objectives.strip()]
            if parsed:
                digests.append(PaperObjectiveDigest(id=paper_id, title=title, objectives=tuple(parsed)))
        return digests

    def _load_project_resources(
        self,
        project_id: UUID,
        resource_scope: Optional[Sequence[ProjectDiscussionResourceType]] = None,
        specific_ids: Optional[dict] = None,
    ) -> List[ResourceDigest]:
        """Load resources from the project, optionally filtered by specific IDs.

        Args:
            project_id: The project ID to load resources from
            resource_scope: Optional filter by resource type (PAPER, REFERENCE, MEETING)
            specific_ids: Optional dict with paper_ids, reference_ids, meeting_ids sets
                         If provided, only load resources with those specific IDs
        """
        resources: List[ResourceDigest] = []
        allowed: Optional[set[ProjectDiscussionResourceType]] = None
        if resource_scope:
            allowed = {ProjectDiscussionResourceType(item) for item in resource_scope}

        # Extract specific ID sets if provided
        specific_paper_ids = specific_ids.get("paper_ids") if specific_ids else None
        specific_reference_ids = specific_ids.get("reference_ids") if specific_ids else None
        specific_meeting_ids = specific_ids.get("meeting_ids") if specific_ids else None

        # Always load paper IDs for reference lookup
        papers: List[ResearchPaper] = []
        paper_ids: List[UUID] = []

        # Load project papers (filtered by specific IDs if provided)
        should_load_papers = (
            (not allowed or ProjectDiscussionResourceType.PAPER in allowed or ProjectDiscussionResourceType.REFERENCE in allowed) and
            (specific_ids is None or specific_paper_ids or specific_reference_ids)
        )
        if should_load_papers:
            query = self.db.query(ResearchPaper).filter(
                ResearchPaper.project_id == project_id,
            )
            # If specific paper IDs given, filter to only those
            if specific_paper_ids:
                query = query.filter(ResearchPaper.id.in_(specific_paper_ids))

            papers = query.all()
            paper_ids = [p.id for p in papers]

            # Add papers to resources if in scope
            should_add_papers = (
                (not allowed or ProjectDiscussionResourceType.PAPER in allowed) and
                (specific_ids is None or specific_paper_ids)
            )
            if should_add_papers:
                for paper in papers:
                    # Skip if specific IDs provided and this paper is not in the list
                    if specific_paper_ids and paper.id not in specific_paper_ids:
                        continue
                    metadata: List[str] = []
                    if paper.status:
                        metadata.append(str(paper.status))
                    # Extract content preview and authoring mode for AI editing
                    content_preview = self._get_paper_content_preview(paper)
                    authoring_mode = self._get_authoring_mode(paper)
                    resources.append(
                        ResourceDigest(
                            id=paper.id,
                            resource_type=ProjectDiscussionResourceType.PAPER,
                            title=paper.title or "Untitled Paper",
                            summary=self._truncate_text(paper.abstract) if paper.abstract else None,
                            metadata=tuple(metadata),
                            content_preview=content_preview,
                            authoring_mode=authoring_mode,
                        )
                    )

        # Load project library references (via ProjectReference table)
        should_load_refs = (
            (not allowed or ProjectDiscussionResourceType.REFERENCE in allowed) and
            (specific_ids is None or specific_reference_ids)
        )
        if should_load_refs:
            from app.models import ProjectReference, ProjectReferenceStatus
            # Join ProjectReference with Reference to get project library references
            query = (
                self.db.query(Reference)
                .join(ProjectReference, ProjectReference.reference_id == Reference.id)
                .filter(
                    ProjectReference.project_id == project_id,
                    ProjectReference.status == ProjectReferenceStatus.APPROVED,
                )
            )
            # If specific reference IDs given, filter to only those
            if specific_reference_ids:
                query = query.filter(Reference.id.in_(specific_reference_ids))

            refs = query.all()
            for ref in refs:
                metadata: List[str] = []
                if ref.source:
                    metadata.append(str(ref.source))
                if ref.year:
                    metadata.append(str(ref.year))
                resources.append(
                    ResourceDigest(
                        id=ref.id,
                        resource_type=ProjectDiscussionResourceType.REFERENCE,
                        title=ref.title or "Untitled Reference",
                        summary=self._truncate_text(ref.abstract) if ref.abstract else None,
                        metadata=tuple(metadata),
                    )
                )

        # Load project meetings (filtered by specific IDs if provided)
        should_load_meetings = (
            (not allowed or ProjectDiscussionResourceType.MEETING in allowed) and
            (specific_ids is None or specific_meeting_ids)
        )
        if should_load_meetings:
            query = self.db.query(Meeting).filter(Meeting.project_id == project_id)
            # If specific meeting IDs given, filter to only those
            if specific_meeting_ids:
                query = query.filter(Meeting.id.in_(specific_meeting_ids))

            meetings = query.all()
            for meeting in meetings:
                # Handle transcript - it's JSONB so convert to string if it's a dict
                transcript_text = None
                if hasattr(meeting, 'transcript') and meeting.transcript:
                    if isinstance(meeting.transcript, dict):
                        # Extract text from transcript dict if possible
                        transcript_text = meeting.transcript.get('text', str(meeting.transcript))
                    else:
                        transcript_text = str(meeting.transcript)

                # Skip meetings without meaningful content
                # Require at least 50 characters of transcript to be considered useful
                MIN_TRANSCRIPT_LENGTH = 50
                has_meaningful_summary = (
                    meeting.summary and
                    meeting.summary.strip() and
                    not meeting.summary.strip().lower().startswith('sync space')
                )
                has_meaningful_transcript = bool(
                    transcript_text and
                    transcript_text.strip() and
                    len(transcript_text.strip()) >= MIN_TRANSCRIPT_LENGTH
                )
                if not has_meaningful_summary and not has_meaningful_transcript:
                    continue

                metadata: List[str] = []
                if hasattr(meeting, 'status') and meeting.status:
                    metadata.append(str(meeting.status))
                if has_transcript:
                    metadata.append("Transcript available")

                resources.append(
                    ResourceDigest(
                        id=meeting.id,
                        resource_type=ProjectDiscussionResourceType.MEETING,
                        title=meeting.summary or f"Meeting {meeting.id}",
                        summary=self._truncate_text(transcript_text) if transcript_text else None,
                        metadata=tuple(metadata),
                    )
                )

        return resources

    def _truncate_text(self, text: str, limit: int = 320) -> str:
        """Truncate text to a maximum length."""
        if not text:
            return ""
        if len(text) <= limit:
            return text
        return text[: limit - 1].rstrip() + "…"

    def _get_paper_content_preview(self, paper, max_chars: int = 2000) -> Optional[str]:
        """Extract paper content for AI context."""
        if isinstance(paper.content_json, dict):
            if paper.content_json.get('authoring_mode') == 'latex':
                latex_source = paper.content_json.get('latex_source', '')
                if latex_source:
                    return latex_source[:max_chars] if len(latex_source) > max_chars else latex_source
        # Rich text fallback
        if paper.content:
            return paper.content[:max_chars] if len(paper.content) > max_chars else paper.content
        return None

    def _get_authoring_mode(self, paper) -> Optional[str]:
        """Get paper authoring mode (latex or rich)."""
        if isinstance(paper.content_json, dict):
            return paper.content_json.get('authoring_mode', 'rich')
        return 'rich' if paper.content else None
