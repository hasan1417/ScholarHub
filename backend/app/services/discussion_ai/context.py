from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy.orm import Session, joinedload

from app.models import (
    Project,
    ProjectDiscussionChannel,
    ProjectDiscussionChannelResource,
    ProjectDiscussionMessage,
    ProjectDiscussionResourceType,
    ProjectDiscussionTask,
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
                metadata.append(details["status"])
            if details.get("year"):
                metadata.append(str(details["year"]))
        elif resource_type == ProjectDiscussionResourceType.REFERENCE:
            if details.get("source"):
                metadata.append(details["source"])
        elif resource_type == ProjectDiscussionResourceType.MEETING:
            if details.get("status"):
                metadata.append(details["status"])
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
        resources = self._load_resources(channel, resource_scope)
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
            resources=resources,
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
