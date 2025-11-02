from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID

class ResearchPaperBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=255, description="Title of the research paper")
    abstract: Optional[str] = Field(None, description="Abstract or summary of the paper")
    keywords: Optional[List[str]] = Field(None, description="Array of keywords")
    paper_type: str = Field(default="research", description="Type of paper (research, review, case_study, etc.)")
    is_public: bool = Field(default=False, description="Whether the paper is publicly visible")
    project_id: Optional[UUID] = Field(None, description="Owning project for this paper")
    format: Optional[str] = Field(None, description="Editor format for the paper (latex, rtf)")

    # Accept keywords as either a comma-separated string or a list, and normalize to List[str]
    @field_validator("keywords", mode="before")
    @classmethod
    def _coerce_keywords(cls, v):
        if v is None:
            return None
        if isinstance(v, str):
            parts = [s.strip() for s in v.split(",") if s.strip()]
            return parts or None
        if isinstance(v, list):
            return [str(s).strip() for s in v if str(s).strip()]
        return v

class ResearchPaperCreate(ResearchPaperBase):
    content: Optional[str] = Field(None, description="Initial content for papers created from scratch")
    content_json: Optional[Dict[str, Any]] = Field(None, description="Rich text content in TipTap JSON format")
    references: Optional[str] = Field(None, description="Bibliography or references")
    summary: Optional[str] = Field(None, description="Short summary of the paper")

class ResearchPaperUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    abstract: Optional[str] = None
    content: Optional[str] = None
    content_json: Optional[Dict[str, Any]] = Field(None, description="Rich text content in TipTap JSON format")
    keywords: Optional[List[str]] = None
    references: Optional[str] = None
    status: Optional[str] = Field(None, description="draft, in_progress, completed, published")
    paper_type: Optional[str] = None
    is_public: Optional[bool] = None
    project_id: Optional[UUID] = None
    format: Optional[str] = None
    summary: Optional[str] = None

class ResearchPaperResponse(ResearchPaperBase):
    id: UUID
    owner_id: UUID
    project_id: Optional[UUID] = None
    status: str
    content: Optional[str] = None
    content_json: Optional[Dict[str, Any]] = None
    references: Optional[str] = None
    current_version: Optional[str] = None
    format: Optional[str] = None
    summary: Optional[str] = None
    
    # Discovery metadata
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    authors: Optional[List[str]] = None
    journal: Optional[str] = None
    description: Optional[str] = None
    
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ResearchPaperList(BaseModel):
    papers: List[ResearchPaperResponse]
    total: int
    skip: int
    limit: int
