"""
PDF Annotations API - CRUD for highlights, notes, and underlines on document PDFs.
"""

import logging
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.database import get_db
from app.models.annotation import PdfAnnotation
from app.models.document import Document
from app.models.paper_member import PaperMember
from app.models.research_paper import ResearchPaper
from app.models.user import User
from app.schemas.annotation import (
    AnnotationCreate,
    AnnotationUpdate,
    AnnotationResponse,
    AnnotationListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _check_document_access(db: Session, document_id: UUID, user: User) -> Document:
    """Verify the document exists and the user has access (owner or paper collaborator)."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    # Access check: owner or collaborator on the associated paper
    has_access = False
    if doc.owner_id == user.id:
        has_access = True
    elif doc.paper_id:
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == doc.paper_id).first()
        if paper and paper.owner_id == user.id:
            has_access = True
        else:
            member = db.query(PaperMember).filter(
                PaperMember.paper_id == doc.paper_id,
                PaperMember.user_id == user.id,
                PaperMember.status == "accepted",
            ).first()
            if member:
                has_access = True

    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied",
        )
    return doc


def _annotation_to_response(ann: PdfAnnotation) -> AnnotationResponse:
    return AnnotationResponse(
        id=ann.id,
        document_id=ann.document_id,
        user_id=ann.user_id,
        page_number=ann.page_number,
        type=ann.type,
        color=ann.color or "#FFEB3B",
        content=ann.content,
        position_data=ann.position_data,
        selected_text=ann.selected_text,
        created_at=ann.created_at,
        updated_at=ann.updated_at,
    )


# ── List annotations for a document ─────────────────────────────────────────

@router.get(
    "/documents/{document_id}/annotations",
    response_model=AnnotationListResponse,
)
def list_annotations(
    document_id: UUID,
    page: Optional[int] = Query(None, ge=0, description="Filter by page number"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all annotations the current user has created on this document."""
    _check_document_access(db, document_id, current_user)

    query = db.query(PdfAnnotation).filter(
        PdfAnnotation.document_id == document_id,
        PdfAnnotation.user_id == current_user.id,
    )

    if page is not None:
        query = query.filter(PdfAnnotation.page_number == page)

    annotations = query.order_by(PdfAnnotation.page_number, PdfAnnotation.created_at).all()

    return AnnotationListResponse(
        annotations=[_annotation_to_response(a) for a in annotations],
        total=len(annotations),
    )


# ── Create annotation ───────────────────────────────────────────────────────

@router.post(
    "/documents/{document_id}/annotations",
    response_model=AnnotationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_annotation(
    document_id: UUID,
    data: AnnotationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new annotation on a document."""
    _check_document_access(db, document_id, current_user)

    annotation = PdfAnnotation(
        document_id=document_id,
        user_id=current_user.id,
        page_number=data.page_number,
        type=data.type,
        color=data.color,
        content=data.content,
        position_data=data.position_data,
        selected_text=data.selected_text,
    )

    db.add(annotation)
    db.commit()
    db.refresh(annotation)

    return _annotation_to_response(annotation)


# ── Update annotation ───────────────────────────────────────────────────────

@router.patch(
    "/annotations/{annotation_id}",
    response_model=AnnotationResponse,
)
def update_annotation(
    annotation_id: UUID,
    data: AnnotationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an annotation (content, color, or position)."""
    annotation = db.query(PdfAnnotation).filter(PdfAnnotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Annotation not found",
        )

    if annotation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only edit your own annotations",
        )

    if data.content is not None:
        annotation.content = data.content
    if data.color is not None:
        annotation.color = data.color
    if data.position_data is not None:
        annotation.position_data = data.position_data

    db.commit()
    db.refresh(annotation)

    return _annotation_to_response(annotation)


# ── Delete annotation ────────────────────────────────────────────────────────

@router.delete(
    "/annotations/{annotation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_annotation(
    annotation_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete an annotation."""
    annotation = db.query(PdfAnnotation).filter(PdfAnnotation.id == annotation_id).first()
    if not annotation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Annotation not found",
        )

    if annotation.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own annotations",
        )

    db.delete(annotation)
    db.commit()
