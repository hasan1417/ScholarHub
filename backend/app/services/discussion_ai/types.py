from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, List, Optional, Sequence
from uuid import UUID

from app.models.project_discussion import ProjectDiscussionResourceType


@dataclass(slots=True)
class MessageDigest:
    id: UUID
    author_name: str
    author_id: Optional[UUID]
    content: str
    created_at: datetime
    parent_id: Optional[UUID] = None


@dataclass(slots=True)
class ResourceDigest:
    id: UUID
    resource_type: ProjectDiscussionResourceType
    title: str
    summary: Optional[str]
    metadata: Sequence[str] = field(default_factory=tuple)
    content_preview: Optional[str] = None  # Paper content for AI editing
    authoring_mode: Optional[str] = None   # 'latex' or 'rich' for papers


@dataclass(slots=True)
class PaperObjectiveDigest:
    id: UUID
    title: str
    objectives: Sequence[str] = field(default_factory=tuple)


@dataclass(slots=True)
class TaskDigest:
    id: UUID
    title: str
    status: str
    summary: Optional[str]
    due_date: Optional[datetime]


@dataclass(slots=True)
class RetrievalSnippet:
    origin: str
    origin_id: UUID
    content: str
    score: float
    metadata: Optional[dict] = None


@dataclass(slots=True)
class AssistantCitation:
    origin: str
    origin_id: UUID
    label: str
    resource_type: Optional[str] = None


@dataclass(slots=True)
class AssistantReply:
    message: str
    citations: Sequence[AssistantCitation]
    reasoning_used: bool
    model: str
    usage: Optional[dict] = None
    suggested_actions: Sequence['AssistantSuggestedAction'] = field(default_factory=tuple)


@dataclass(slots=True)
class AssistantSuggestedAction:
    action_type: str
    summary: str
    payload: dict


@dataclass(slots=True)
class SearchResultDigest:
    """A paper from recent search results."""
    title: str
    authors: Optional[str] = None
    year: Optional[int] = None
    source: Optional[str] = None


@dataclass(slots=True)
class ChannelContext:
    project_id: UUID
    project_title: str
    channel_id: UUID
    channel_name: str
    channel_description: Optional[str]
    summary: Optional[str]
    messages: Sequence[MessageDigest]
    resources: Sequence[ResourceDigest]
    tasks: Sequence[TaskDigest]
    project_objectives: Sequence[str] = field(default_factory=tuple)
    paper_objectives: Sequence[PaperObjectiveDigest] = field(default_factory=tuple)
    resource_scope: Sequence[ProjectDiscussionResourceType] = field(default_factory=tuple)
    recent_search_results: Sequence[SearchResultDigest] = field(default_factory=tuple)

    @property
    def message_window(self) -> Sequence[MessageDigest]:
        return self.messages

    @property
    def resource_index(self) -> Iterable[ResourceDigest]:
        return self.resources
