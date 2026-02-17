from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from uuid import UUID


class AnnotationCreate(BaseModel):
    page_number: int = Field(..., ge=0, description="Zero-indexed page number")
    type: str = Field(..., pattern="^(highlight|note|underline)$", description="Annotation type")
    color: str = Field(default="#FFEB3B", pattern="^#[0-9A-Fa-f]{6}$", description="Hex color")
    content: Optional[str] = Field(None, description="Text note content")
    position_data: Dict[str, Any] = Field(..., description="PDF coordinate data")
    selected_text: Optional[str] = Field(None, description="Highlighted text")


class AnnotationUpdate(BaseModel):
    content: Optional[str] = None
    color: Optional[str] = Field(None, pattern="^#[0-9A-Fa-f]{6}$")
    position_data: Optional[Dict[str, Any]] = None


class AnnotationResponse(BaseModel):
    id: UUID
    document_id: UUID
    user_id: UUID
    page_number: int
    type: str
    color: str
    content: Optional[str] = None
    position_data: Dict[str, Any]
    selected_text: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AnnotationListResponse(BaseModel):
    annotations: List[AnnotationResponse]
    total: int
