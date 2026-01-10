from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, model_validator, field_validator



class DiscussionMessageCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)
    channel_id: Optional[UUID] = None
    parent_id: Optional[UUID] = None


class DiscussionMessageUpdate(BaseModel):
    content: str = Field(..., min_length=1, max_length=10000)


class DiscussionMessageUserInfo(BaseModel):
    id: UUID
    name: str
    email: str

    class Config:
        from_attributes = True


class DiscussionMessageAttachmentResponse(BaseModel):
    id: UUID
    message_id: UUID
    attachment_type: str
    title: Optional[str] = None
    url: Optional[str] = None
    document_id: Optional[UUID] = None
    paper_id: Optional[UUID] = None
    reference_id: Optional[UUID] = None
    meeting_id: Optional[UUID] = None
    details: Dict[str, Any]
    created_at: datetime
    created_by: Optional[UUID] = None

    class Config:
        from_attributes = True


class DiscussionMessageResponse(BaseModel):
    id: UUID
    project_id: UUID
    channel_id: UUID
    user_id: UUID
    user: DiscussionMessageUserInfo
    content: str
    parent_id: Optional[UUID] = None
    is_edited: bool
    is_deleted: bool
    created_at: datetime
    updated_at: datetime
    reply_count: int = 0
    attachments: List[DiscussionMessageAttachmentResponse] = []

    class Config:
        from_attributes = True


class DiscussionThreadResponse(BaseModel):
    message: DiscussionMessageResponse
    replies: List[DiscussionMessageResponse] = []

    class Config:
        from_attributes = True


class DiscussionStats(BaseModel):
    project_id: UUID
    total_messages: int
    total_threads: int
    channel_id: Optional[UUID] = None

    class Config:
        from_attributes = True


class ChannelScopeConfig(BaseModel):
    """Specific resource IDs for channel scope. null = project-wide (all resources)."""
    paper_ids: Optional[List[UUID]] = None
    reference_ids: Optional[List[UUID]] = None
    meeting_ids: Optional[List[UUID]] = None

    def is_empty(self) -> bool:
        """Check if all ID lists are empty or None."""
        return (
            (not self.paper_ids or len(self.paper_ids) == 0) and
            (not self.reference_ids or len(self.reference_ids) == 0) and
            (not self.meeting_ids or len(self.meeting_ids) == 0)
        )


class DiscussionChannelBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    slug: Optional[str] = Field(default=None, max_length=255)


class DiscussionChannelCreate(DiscussionChannelBase):
    # null = project-wide (all resources), or specific resource IDs
    scope: Optional[ChannelScopeConfig] = None


class DiscussionChannelUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    is_archived: Optional[bool] = None
    # null = don't change, empty object = project-wide, or specific resource IDs
    scope: Optional[ChannelScopeConfig] = Field(default=None)


class DiscussionChannelSummary(BaseModel):
    id: UUID
    project_id: UUID
    name: str
    slug: str
    description: Optional[str]
    is_default: bool
    is_archived: bool
    scope: Optional[ChannelScopeConfig] = None  # null = project-wide, or specific resource IDs
    created_at: datetime
    updated_at: datetime
    stats: Optional[DiscussionStats] = None

    class Config:
        from_attributes = True


class ChannelResourceBase(BaseModel):
    resource_type: Literal["paper", "reference", "meeting"]
    paper_id: Optional[UUID] = None
    reference_id: Optional[UUID] = None
    meeting_id: Optional[UUID] = None
    details: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_resource_target(self) -> "ChannelResourceBase":
        required_field_map = {
            "paper": "paper_id",
            "reference": "reference_id",
            "meeting": "meeting_id",
        }

        required_field = required_field_map[self.resource_type]
        target_value = getattr(self, required_field)
        if target_value is None:
            raise ValueError(f"{self.resource_type} resources require {required_field}")

        for field_name in required_field_map.values():
            if field_name == required_field:
                continue
            if getattr(self, field_name) is not None:
                raise ValueError(f"{field_name} is not valid for resource type {self.resource_type}")

        return self


class DiscussionChannelResourceCreate(ChannelResourceBase):
    pass


class DiscussionChannelResourceResponse(ChannelResourceBase):
    id: UUID
    channel_id: UUID
    added_by: Optional[UUID]
    created_at: datetime

    class Config:
        from_attributes = True


class DiscussionTaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    assignee_id: Optional[UUID] = None
    due_date: Optional[datetime] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    message_id: Optional[UUID] = None


class DiscussionTaskCreate(DiscussionTaskBase):
    pass


class DiscussionTaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=5000)
    status: Optional[Literal["open", "in_progress", "completed", "cancelled"]] = None
    assignee_id: Optional[UUID] = None
    due_date: Optional[datetime] = None
    details: Optional[Dict[str, Any]] = None


class DiscussionTaskResponse(DiscussionTaskBase):
    id: UUID
    project_id: UUID
    channel_id: UUID
    message_id: Optional[UUID]
    status: str
    created_by: Optional[UUID]
    updated_by: Optional[UUID]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class DiscussionAssistantCitation(BaseModel):
    origin: Literal["resource", "message"]
    origin_id: UUID
    label: str
    resource_type: Optional[str] = None


class DiscussionAssistantSuggestedAction(BaseModel):
    action_type: str
    summary: str
    payload: Dict[str, Any]

ALLOWED_ASSISTANT_SCOPE = {"transcripts", "papers", "references"}


class DiscussionAssistantRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=5000)
    reasoning: bool = False
    scope: Optional[List[str]] = None

    @field_validator("scope")
    @classmethod
    def _normalize_scope(cls, value: Optional[List[str]]):
        if not value:
            return None
        normalized: List[str] = []
        for entry in value:
            if not entry:
                continue
            lowered = entry.strip().lower()
            if lowered in ALLOWED_ASSISTANT_SCOPE and lowered not in normalized:
                normalized.append(lowered)
        return normalized or None


class DiscussionAssistantResponse(BaseModel):
    message: str
    citations: List[DiscussionAssistantCitation]
    reasoning_used: bool
    model: str
    usage: Optional[Dict[str, Any]] = None
    suggested_actions: List[DiscussionAssistantSuggestedAction] = Field(default_factory=list)


DiscussionAssistantResponse.model_rebuild(_types_namespace=globals())


class DiscussionAssistantExchangeResponse(BaseModel):
    id: UUID
    question: str
    response: DiscussionAssistantResponse
    created_at: datetime
    author: Optional[Dict[str, Any]] = None


DiscussionAssistantExchangeResponse.model_rebuild(_types_namespace=globals())
