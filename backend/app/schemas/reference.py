from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
import uuid

class ReferenceCreate(BaseModel):
    title: str
    authors: List[str] = []
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    is_open_access: Optional[bool] = False
    pdf_url: Optional[str] = None
    journal: Optional[str] = None
    abstract: Optional[str] = None

class ReferenceResponse(BaseModel):
    id: uuid.UUID
    paper_id: Optional[uuid.UUID] = None
    title: str
    authors: List[str] = []
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: Optional[str] = None
    is_open_access: Optional[bool] = False
    pdf_url: Optional[str] = None
    journal: Optional[str] = None
    abstract: Optional[str] = None
    status: str
    document_id: Optional[uuid.UUID] = None
    summary: Optional[str] = None
    key_findings: Optional[List[str]] = None
    methodology: Optional[str] = None
    limitations: Optional[List[str]] = None
    relevance_score: Optional[float] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class ReferenceList(BaseModel):
    references: List[ReferenceResponse]
    total: int
