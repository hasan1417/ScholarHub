from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class PaperVersionBase(BaseModel):
    version_number: str = Field(..., description="Version number (e.g., '1.0', '1.1', '2.0')")
    title: str = Field(..., min_length=1, max_length=255, description="Title at this version")
    abstract: Optional[str] = Field(None, description="Abstract at this version")
    keywords: Optional[str] = Field(None, description="Keywords at this version")
    references: Optional[str] = Field(None, description="References at this version")
    change_summary: Optional[str] = Field(None, description="Summary of changes in this version")


class PaperVersionCreate(PaperVersionBase):
    content: Optional[str] = Field(None, description="Plain text content")
    content_json: Optional[Dict[str, Any]] = Field(None, description="Rich text content in TipTap JSON format")


class PaperVersionResponse(PaperVersionBase):
    id: UUID
    paper_id: UUID
    content: Optional[str] = None
    content_json: Optional[Dict[str, Any]] = None
    created_by: Optional[UUID] = None
    created_at: datetime
    
    class Config:
        from_attributes = True


class PaperVersionList(BaseModel):
    versions: List[PaperVersionResponse]
    total: int
    current_version: str


class ContentUpdateRequest(BaseModel):
    content: Optional[str] = Field(None, description="Plain text content")
    content_json: Optional[Dict[str, Any]] = Field(None, description="Rich text content in TipTap JSON format")
    save_as_version: bool = Field(False, description="Whether to save as a new version")
    version_summary: Optional[str] = Field(None, description="Summary of changes for new version")
    manual_save: bool = Field(False, description="True if user clicked save button (always creates snapshot)")