from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
import json
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.research_paper import ResearchPaper
from app.models.paper_member import PaperMember, PaperRole
from app.models.document import Document, DocumentStatus, DocumentType
from app.models.document_chunk import DocumentChunk
from app.schemas.document import DocumentResponse, DocumentUpdate, DocumentCreate, DocumentList
from app.services.document_service import DocumentService
from app.services.ai_service import AIService
from sqlalchemy import func
import logging
from app.models.document_tag import DocumentTag
import aiohttp
import mimetypes
from fastapi.responses import FileResponse
import os

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])

# Initialize services
document_service = DocumentService()
ai_service = AIService()

@router.post("/upload", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    paper_id: Optional[str] = Form(None),
    tags: Optional[str] = Form(None),  # JSON string of tag names
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a new document"""
    # Validate file type
    allowed_types = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "text/plain"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400, 
            detail="Unsupported file type. Only PDF, DOCX, and TXT files are allowed."
        )
    
    # Validate file size (10MB limit)
    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size too large. Maximum size is 10MB.")
    
    # Parse tags if provided
    tag_names = []
    if tags:
        try:
            tag_names = json.loads(tags)
            if not isinstance(tag_names, list):
                raise ValueError("Tags must be a list")
        except (json.JSONDecodeError, ValueError):
            raise HTTPException(status_code=400, detail="Invalid tags format")
    
    # Validate paper access if paper_id is provided
    if paper_id:
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Research paper not found")
        
        # Check if user has access to this paper
        if paper.owner_id != current_user.id:
            member = db.query(PaperMember).filter(
                PaperMember.paper_id == paper_id,
                PaperMember.user_id == current_user.id
            ).first()
            if not member or member.status != "accepted":
                raise HTTPException(status_code=403, detail="Access denied to paper")

            allowed_roles = {PaperRole.OWNER, PaperRole.ADMIN, PaperRole.EDITOR}
            if member.role not in allowed_roles:
                raise HTTPException(status_code=403, detail="Insufficient permissions to upload documents")
    
    try:
        # Read file content
        file_content = await file.read()
        
        # Calculate file hash for duplicate detection
        file_hash = document_service.duplicate_detector.calculate_file_hash(file_content)
        
        # Check for duplicates before saving
        duplicate_check = document_service.check_for_duplicates(
            db, file_content, file.filename, "", current_user.id
        )
        
        # If exact duplicate found, return error
        if duplicate_check.get('exact_duplicate'):
            duplicate_doc = duplicate_check['exact_duplicate']
            raise HTTPException(
                status_code=409, 
                detail={
                    "message": "This file appears to be an exact duplicate of an existing document.",
                    "duplicate_document": {
                        "id": str(duplicate_doc.id),
                        "title": duplicate_doc.title or duplicate_doc.original_filename,
                        "uploaded_at": duplicate_doc.created_at.isoformat()
                    },
                    "duplicate_check_results": {
                        "exact_duplicate": {
                            "id": str(duplicate_doc.id),
                            "title": duplicate_doc.title or duplicate_doc.original_filename,
                            "filename": duplicate_doc.original_filename,
                            "uploaded_at": duplicate_doc.created_at.isoformat()
                        },
                        "filename_similarities": [],
                        "content_similarities": [],
                        "recommendation": "exact_duplicate_found"
                    }
                }
            )
        
        # Save file to disk
        file_path = await document_service.save_uploaded_file(file_content, file.filename)
        
        # Detect document type
        document_type = document_service.detect_document_type(file_path, file.content_type or "")
        
        # Create document record
        document = Document(
            filename=file.filename,
            original_filename=file.filename,
            file_path=file_path,
            file_size=len(file_content),
            mime_type=file.content_type,
            document_type=document_type,
            file_hash=file_hash,  # Store the file hash
            title=title,
            owner_id=current_user.id,
            paper_id=paper_id
        )
        
        db.add(document)
        db.commit()
        db.refresh(document)
        
        # Process document asynchronously (in production, use background tasks)
        try:
            await document_service.process_document(db, document, file_content, tag_names)
        except Exception as e:
            # Log error but don't fail the upload
            print(f"Error processing document {document.id}: {e}")
        
        return document
        
    except HTTPException:
        # Re-raise HTTP exceptions (like 409 for duplicates) without modification
        raise
    except Exception as e:
        import traceback
        print(f"Error uploading document: {str(e)}")
        print(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Error uploading document: {str(e)}")

@router.post("/create", response_model=DocumentResponse)
async def create_document(
    document_data: DocumentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Create a new document for the rich text editor
    """
    try:
        # Create new document
        new_document = Document(
            title=document_data.title,
            content=document_data.content or "",
            owner_id=current_user.id,
            project_id=document_data.project_id,
            document_type=DocumentType.RESEARCH_PAPER,
            status=DocumentStatus.PROCESSED,
            is_processed_for_ai=True  # Mark as processed since it's text content
        )
        
        db.add(new_document)
        db.commit()
        db.refresh(new_document)
        
        logger.info(f"Created document {new_document.id} for user {current_user.id}")
        
        return DocumentResponse(
            id=str(new_document.id),
            title=new_document.title,
            content=new_document.content,
            project_id=str(new_document.project_id) if new_document.project_id else None,
            created_at=new_document.created_at,
            updated_at=new_document.updated_at
        )
        
    except Exception as e:
        logger.error(f"Error creating document: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create document"
        )

@router.get("/list", response_model=DocumentList)
async def list_documents(
    project_id: Optional[str] = None,  # Keep for backward compatibility
    paper_id: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    List documents for the current user. 
    If paper_id is provided, shows all documents for that paper from any collaborator.
    Otherwise, shows only the user's own documents.
    """
    try:
        # Use paper_id if provided, fallback to project_id for backward compatibility
        target_paper_id = paper_id or project_id
        
        if target_paper_id:
            # When viewing documents for a specific paper, show documents from ALL collaborators
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == target_paper_id).first()
            if not paper:
                raise HTTPException(status_code=404, detail="Research paper not found")
            
            # Check if user has access to this paper (owner or member)
            has_access = False
            if paper.owner_id == current_user.id:
                has_access = True
            else:
                member = db.query(PaperMember).filter(
                    PaperMember.paper_id == target_paper_id,
                    PaperMember.user_id == current_user.id,
                    PaperMember.status == "accepted"
                ).first()
                if member:
                    has_access = True
            
            if not has_access:
                raise HTTPException(status_code=403, detail="Access denied to paper documents")
            
            # Get all documents for this paper from any collaborator, with owner info
            query = db.query(Document).filter(Document.paper_id == target_paper_id)
        else:
            # When not viewing a specific paper, show only user's own documents
            query = db.query(Document).filter(Document.owner_id == current_user.id)
        
        # Load owner relationship for all documents
        documents = query.order_by(Document.updated_at.desc()).offset(skip).limit(limit).all()
        
        # Get total count for pagination
        total_count = query.count()
        
        # Ensure owner relationships are loaded
        for doc in documents:
            if not hasattr(doc, 'owner') or doc.owner is None:
                doc.owner = db.query(User).filter(User.id == doc.owner_id).first()
        
        return DocumentList(
            documents=[
                {
                    "id": str(doc.id),
                    "title": doc.title or doc.original_filename,
                    "file_name": doc.original_filename,  # Frontend expects this field
                    "file_path": doc.file_path,
                    "file_size": doc.file_size or 0,
                    "mime_type": doc.mime_type,
                    "document_type": doc.document_type.value if doc.document_type else "unknown",
                    "status": doc.status.value if doc.status else "unknown",
                    "extracted_text": doc.extracted_text,
                    "page_count": doc.page_count,
                    "abstract": doc.abstract,
                    "authors": doc.authors,
                    "publication_year": doc.publication_year,
                    "journal": doc.journal,
                    "doi": doc.doi,
                    "owner_id": str(doc.owner_id),
                    "owner_name": f"{doc.owner.first_name} {doc.owner.last_name}".strip() if doc.owner else "Unknown",
                    "paper_id": str(doc.paper_id) if doc.paper_id else None,
                    "is_processed_for_ai": doc.is_processed_for_ai,
                    "processed_at": doc.processed_at.isoformat() if doc.processed_at else None,
                    "created_at": doc.created_at.isoformat(),
                    "updated_at": doc.updated_at.isoformat()
                }
                for doc in documents
            ],
            total=total_count
        )
        
    except Exception as e:
        logger.error(f"Error listing documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list documents"
        )

@router.get("/{document_id}/download")
async def download_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download the original file for a document (PDF/DOCX/TXT). Access rules same as get_document."""
    doc: Document = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Access check (owner or collaborator on paper)
    has_access = False
    if doc.owner_id == current_user.id:
        has_access = True
    elif doc.paper_id:
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == doc.paper_id).first()
        if paper and paper.owner_id == current_user.id:
            has_access = True
        else:
            member = db.query(PaperMember).filter(
                PaperMember.paper_id == doc.paper_id,
                PaperMember.user_id == current_user.id,
                PaperMember.status == "accepted"
            ).first()
            if member:
                has_access = True
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate path exists
    file_path = doc.file_path
    if not file_path or not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found on server")
    # Guess content type
    ctype = doc.mime_type or mimetypes.guess_type(file_path)[0] or "application/octet-stream"
    filename = doc.original_filename or os.path.basename(file_path)
    return FileResponse(path=file_path, media_type=ctype, filename=filename)

@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get a specific document by ID.
    Users can access their own documents or documents from papers they collaborate on.
    """
    try:
        document = db.query(Document).filter(Document.id == document_id).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Check access: user owns the document OR user is a collaborator on the document's paper
        has_access = False
        
        if document.owner_id == current_user.id:
            has_access = True
        elif document.paper_id:
            # Check if user is a collaborator on this paper
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == document.paper_id).first()
            if paper and paper.owner_id == current_user.id:
                has_access = True
            else:
                member = db.query(PaperMember).filter(
                    PaperMember.paper_id == document.paper_id,
                    PaperMember.user_id == current_user.id,
                    PaperMember.status == "accepted"
                ).first()
                if member:
                    has_access = True
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to document"
            )
        
        return DocumentResponse(
            id=str(document.id),
            title=document.title,
            content=document.content,
            project_id=str(document.project_id) if document.project_id else None,
            created_at=document.created_at,
            updated_at=document.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document"
        )

@router.put("/{document_id}", response_model=DocumentResponse)
async def update_document(
    document_id: str,
    document_data: DocumentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Update a document
    """
    try:
        document = db.query(Document).filter(
            Document.id == document_id,
            Document.owner_id == current_user.id
        ).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Update fields if provided
        if document_data.title is not None:
            document.title = document_data.title
        if document_data.content is not None:
            document.content = document_data.content
        if document_data.project_id is not None:
            document.project_id = document_data.project_id
        
        document.updated_at = func.now()
        db.commit()
        db.refresh(document)
        
        logger.info(f"Updated document {document_id} for user {current_user.id}")
        
        return DocumentResponse(
            id=str(document.id),
            title=document.title,
            content=document.content,
            project_id=str(document.project_id) if document.project_id else None,
            created_at=document.created_at,
            updated_at=document.updated_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating document {document_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update document"
        )

@router.delete("/{document_id}")
async def delete_document(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete a document
    """
    try:
        document = db.query(Document).filter(
            Document.id == document_id,
            Document.owner_id == current_user.id
        ).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Delete related chunks first (since cascade is disabled)
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        for chunk in chunks:
            db.delete(chunk)
        
        # Delete related tags
        tags = db.query(DocumentTag).filter(DocumentTag.document_id == document_id).all()
        for tag in tags:
            db.delete(tag)
        
        # Delete the document
        db.delete(document)
        db.commit()
        
        logger.info(f"Deleted document {document_id} for user {current_user.id}")
        
        return {"message": "Document deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting document {document_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )

@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get chunks for a specific document"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check access: user owns the document OR user is a collaborator on the document's paper
    has_access = False
    
    if document.owner_id == current_user.id:
        has_access = True
    elif document.paper_id:
        # Check if user is a collaborator on this paper
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == document.paper_id).first()
        if paper and paper.owner_id == current_user.id:
            has_access = True
        else:
            member = db.query(PaperMember).filter(
                PaperMember.paper_id == document.paper_id,
                PaperMember.user_id == current_user.id,
                PaperMember.status == "accepted"
            ).first()
            if member:
                has_access = True
    
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")
    
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).offset(skip).limit(limit).all()
    
    total = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).count()
    
    return {"chunks": chunks, "total": total}

@router.post("/{document_id}/analyze")
async def analyze_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze a document using AI"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check access
    if document.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        analysis = await ai_service.analyze_document_content(document, [])
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing document: {str(e)}")

@router.post("/{document_id}/chat")
async def chat_with_document(
    document_id: str,
    question: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Chat with a document using AI"""
    document = db.query(Document).filter(Document.id == document_id).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Check access: user owns the document OR user is a collaborator on the document's paper
    has_access = False
    
    if document.owner_id == current_user.id:
        has_access = True
    elif document.paper_id:
        # Check if user is a collaborator on this paper
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == document.paper_id).first()
        if paper and paper.owner_id == current_user.id:
            has_access = True
        else:
            member = db.query(PaperMember).filter(
                PaperMember.paper_id == document.paper_id,
                PaperMember.user_id == current_user.id,
                PaperMember.status == "accepted"
            ).first()
            if member:
                has_access = True
    
    if not has_access:
        raise HTTPException(status_code=403, detail="Access denied")
    
    try:
        # Get document chunks for context
        chunks = db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).all()
        
        response = await ai_service.answer_question_from_context(question, chunks)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error chatting with document: {str(e)}")
@router.post("/ingest-remote", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def ingest_remote_document(
    url: str = Form(..., description="Direct PDF URL"),
    title: Optional[str] = Form(None),
    doi: Optional[str] = Form(None),
    journal: Optional[str] = Form(None),
    year: Optional[int] = Form(None),
    paper_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Download a remote PDF and ingest it as a document for AI processing.

    Notes:
    - Only supports PDFs (application/pdf). If the URL is not a PDF, returns 400.
    - Applies duplicate detection before saving.
    - Processes the document (extract text and chunk) after saving.
    """
    # Validate paper access if paper_id is provided
    if paper_id:
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
        if not paper:
            raise HTTPException(status_code=404, detail="Research paper not found")
        if paper.owner_id != current_user.id:
            member = db.query(PaperMember).filter(
                PaperMember.paper_id == paper_id,
                PaperMember.user_id == current_user.id
            ).first()
            if not member:
                raise HTTPException(status_code=403, detail="Access denied to paper")

    # Fetch the remote file
    timeout = aiohttp.ClientTimeout(total=20)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, allow_redirects=True) as resp:
                if resp.status != 200:
                    raise HTTPException(status_code=400, detail=f"Failed to fetch URL, status {resp.status}")
                ctype = (resp.headers.get('content-type') or '').lower()
                # Basic check: allow if content-type indicates PDF or URL ends with .pdf
                if 'application/pdf' not in ctype and not url.lower().endswith('.pdf'):
                    raise HTTPException(status_code=400, detail="URL does not point to a PDF")
                file_content = await resp.read()
                if not file_content or len(file_content) < 1000:
                    raise HTTPException(status_code=400, detail="Downloaded file is empty or too small")
                # Derive a filename
                filename = url.split('/')[-1] or 'document.pdf'
                if not filename.lower().endswith('.pdf'):
                    filename = filename + '.pdf'
                mime_type = 'application/pdf'

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error downloading file: {str(e)}")

    # Duplicate detection
    try:
        file_hash = document_service.duplicate_detector.calculate_file_hash(file_content)
        duplicate_check = document_service.check_for_duplicates(
            db, file_content, filename, "", current_user.id
        )
        if duplicate_check.get('exact_duplicate'):
            duplicate_doc = duplicate_check['exact_duplicate']
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "This file appears to be an exact duplicate of an existing document.",
                    "duplicate_document": {
                        "id": str(duplicate_doc.id),
                        "title": duplicate_doc.title or duplicate_doc.original_filename,
                        "uploaded_at": duplicate_doc.created_at.isoformat()
                    }
                }
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Duplicate check failed: {str(e)}")

    # Save file
    try:
        file_path = await document_service.save_uploaded_file(file_content, filename)
        document_type = document_service.detect_document_type(file_path, mime_type)
        document = Document(
            filename=filename,
            original_filename=filename,
            file_path=file_path,
            file_size=len(file_content),
            mime_type=mime_type,
            document_type=document_type,
            file_hash=file_hash,
            title=title or filename,
            doi=doi,
            journal=journal,
            publication_year=year,
            owner_id=current_user.id,
            paper_id=paper_id
        )
        db.add(document)
        db.commit()
        db.refresh(document)

        # Process document (extract text, chunk)
        try:
            await document_service.process_document(db, document, file_content, tags=None)
        except Exception as e:
            logger.error(f"Error processing downloaded document {document.id}: {e}")

        return document
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error saving document: {str(e)}")
