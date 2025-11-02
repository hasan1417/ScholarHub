from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID
from app.models.document import DocumentStatus, DocumentType

class DocumentCreate(BaseModel):
    title: str
    content: Optional[str] = ""
    project_id: Optional[str] = None

class DocumentUpload(BaseModel):
    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    paper_id: Optional[UUID] = Field(None, description="Associated research paper ID")
    tags: Optional[List[str]] = Field(None, description="List of tag names")

class DocumentUpdate(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    project_id: Optional[str] = None

class DocumentResponse(BaseModel):
    id: UUID
    title: str
    content: Optional[str] = None
    project_id: Optional[UUID] = None
    # Additional fields needed by frontend
    filename: Optional[str] = None
    original_filename: Optional[str] = None
    document_type: Optional[str] = None
    status: Optional[str] = None
    page_count: Optional[int] = None
    is_processed_for_ai: Optional[bool] = None
    paper_id: Optional[UUID] = None
    # Collaboration fields
    file_size: Optional[int] = None
    owner_id: Optional[UUID] = None
    owner_name: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    
    @field_validator('id', 'project_id', 'paper_id', 'owner_id', mode='before')
    @classmethod
    def convert_uuid_to_str(cls, v):
        if v is not None:
            return str(v)
        return v
    
    class Config:
        from_attributes = True

class DocumentList(BaseModel):
    documents: List[DocumentResponse]
    total: int
