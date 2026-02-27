from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, computed_field

from app.models.project_member import ProjectRole


class ProjectBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    idea: Optional[str] = None
    keywords: Optional[List[str]] = None
    scope: Optional[str] = None
    status: Optional[str] = Field(default="active")

    @field_validator("keywords", mode="before")
    @classmethod
    def _coerce_keywords(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            parts = [segment.strip() for segment in v.split(",") if segment and segment.strip()]
            return parts or None
        if isinstance(v, list):
            return [str(item).strip() for item in v if str(item).strip()]
        return v


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    idea: Optional[str] = None
    keywords: Optional[List[str]] = None
    scope: Optional[str] = None
    status: Optional[str] = None


MIN_REFRESH_INTERVAL_HOURS = 6  # Minimum auto-refresh every 6 hours


class ProjectDiscoveryPreferences(BaseModel):
    query: Optional[str] = None
    keywords: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    auto_refresh_enabled: bool = False
    refresh_interval_hours: Optional[float] = Field(
        default=None,
        ge=MIN_REFRESH_INTERVAL_HOURS,
        le=720,
    )
    last_run_at: Optional[datetime] = None
    last_result_count: Optional[int] = None
    last_status: Optional[str] = None
    max_results: Optional[int] = None
    relevance_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("keywords", mode="before")
    @classmethod
    def _normalize_keywords(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            parts = [segment.strip() for segment in value.split(",") if segment and segment.strip()]
            return parts or None
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return value

    @field_validator("sources", mode="before")
    @classmethod
    def _normalize_sources(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            parts = [segment.strip() for segment in value.split(",") if segment and segment.strip()]
            return parts or None
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return value


class ProjectMemberSummary(BaseModel):
    """Lightweight member info for project list cards."""
    id: UUID
    user_id: UUID
    role: ProjectRole
    status: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: str

    class Config:
        from_attributes = True


class ProjectSummary(ProjectBase):
    id: UUID
    slug: Optional[str] = None
    short_id: Optional[str] = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    discovery_preferences: Optional[ProjectDiscoveryPreferences] = None
    current_user_role: Optional[str] = None
    current_user_status: Optional[str] = None
    members: Optional[List[ProjectMemberSummary]] = None
    paper_count: int = 0
    reference_count: int = 0

    @computed_field(return_type=str)
    def url_id(self) -> str:
        """URL-friendly identifier: slug-shortid or just shortid."""
        if self.slug and self.short_id:
            return f"{self.slug}-{self.short_id}"
        return self.short_id or str(self.id)

    class Config:
        from_attributes = True


class ProjectList(BaseModel):
    projects: List[ProjectSummary]
    total: int
    skip: int
    limit: int


class ProjectMemberUser(BaseModel):
    id: UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None

    @computed_field(return_type=str)
    def display_name(self) -> str:
        if self.first_name or self.last_name:
            parts = [part for part in [self.first_name, self.last_name] if part]
            return " ".join(parts).strip()
        return self.email

    class Config:
        from_attributes = True


class ProjectMemberBase(BaseModel):
    user_id: UUID
    role: ProjectRole = ProjectRole.EDITOR


class ProjectMemberCreate(ProjectMemberBase):
    pass


class ProjectMemberUpdate(BaseModel):
    role: ProjectRole


class ProjectMemberResponse(ProjectMemberBase):
    id: UUID
    project_id: UUID
    status: str
    invited_by: Optional[UUID] = None
    invited_at: Optional[datetime] = None
    joined_at: Optional[datetime] = None
    user: ProjectMemberUser

    class Config:
        from_attributes = True


class ProjectDetail(ProjectSummary):
    members: List[ProjectMemberResponse] = []


class PendingProjectInvitation(BaseModel):
    project_id: UUID
    project_title: str
    member_id: UUID
    role: ProjectRole
    invited_at: Optional[datetime] = None
    invited_by: Optional[str] = None


class PendingProjectInvitationList(BaseModel):
    invitations: List[PendingProjectInvitation]


class ProjectDiscoveryPreferencesUpdate(BaseModel):
    query: Optional[str] = None
    keywords: Optional[List[str]] = None
    sources: Optional[List[str]] = None
    auto_refresh_enabled: Optional[bool] = None
    refresh_interval_hours: Optional[float] = Field(
        default=None,
        ge=MIN_REFRESH_INTERVAL_HOURS,
        le=720,
    )
    max_results: Optional[int] = Field(default=None, ge=1, le=100)
    relevance_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("keywords", mode="before")
    @classmethod
    def _normalize_keywords(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            parts = [segment.strip() for segment in value.split(",") if segment and segment.strip()]
            return parts or None
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return value

    @field_validator("sources", mode="before")
    @classmethod
    def _normalize_sources(cls, value):
        if value is None:
            return None
        if isinstance(value, str):
            parts = [segment.strip() for segment in value.split(",") if segment and segment.strip()]
            return parts or None
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return value
