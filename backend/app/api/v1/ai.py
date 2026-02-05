from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from app.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.reference import Reference
from openai import OpenAI
import os
import math
from app.services.ai_service import AIService
from app.services.document_processing_service import DocumentProcessingService
from app.schemas.ai import ChatQuery, ChatResponse, DocumentProcessingResponse
from pydantic import BaseModel
import logging
import time
from app.models.paper_reference import PaperReference

logger = logging.getLogger(__name__)

# Pydantic models for API requests
class ModelConfigurationRequest(BaseModel):
    provider: str
    embedding_model: Optional[str] = None
    chat_model: Optional[str] = None

# AI Writing Tools Models
class TextGenerationRequest(BaseModel):
    text: str
    instruction: str  # e.g., "expand", "rephrase", "complete", "summarize"
    context: Optional[str] = None  # Additional context or requirements
    max_length: Optional[int] = 500  # Maximum length of generated text

class TextGenerationResponse(BaseModel):
    generated_text: str
    original_text: str
    instruction: str
    word_count: int
    processing_time: float

class GrammarCheckRequest(BaseModel):
    text: str
    check_grammar: bool = True
    check_style: bool = True
    check_clarity: bool = True

class GrammarCheckResponse(BaseModel):
    corrected_text: str
    original_text: str
    suggestions: List[Dict[str, Any]]
    overall_score: float
    processing_time: float

class ResearchContextRequest(BaseModel):
    text: str
    paper_ids: List[str]  # IDs of papers to use as context
    query_type: str  # "enhance", "cite", "expand", "validate"

class ResearchContextResponse(BaseModel):
    enhanced_text: str
    original_text: str
    suggestions: List[Dict[str, Any]]
    relevant_sources: List[Dict[str, Any]]
    processing_time: float

router = APIRouter()
ai_service = AIService()
document_processor = DocumentProcessingService()


@router.post("/chat-with-documents", response_model=ChatResponse)
async def chat_with_documents(
    query: ChatQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Chat with user's documents using RAG (Retrieval Augmented Generation)
    """
    try:
        logger.info(f"Chat request from user {current_user.id}: {query.query}")
        
        # Check if AI service is ready
        if ai_service.initialization_status != "ready":
            logger.warning("AI service not ready")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not ready. Please try again later."
            )
        
        # Check if user has any processed documents
        processed_docs = db.query(Document).filter(
            Document.owner_id == current_user.id,
            Document.is_processed_for_ai == True
        ).count()
        
        logger.info(f"User {current_user.id} has {processed_docs} processed documents")
        
        if processed_docs == 0:
            logger.warning(f"User {current_user.id} has no processed documents")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No documents processed for AI. Please upload and process some documents first."
            )
        
        # Perform chat with documents
        logger.info(f"Calling AI service for user {current_user.id}")
        result = ai_service.chat_with_documents(db, str(current_user.id), query.query)
        
        logger.info(f"AI service returned result: {result}")
        logger.info(f"Result type: {type(result)}")
        logger.info(f"Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        
        # Check if result has required keys
        if not isinstance(result, dict):
            logger.error(f"AI service returned non-dict result: {type(result)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI service returned invalid result format"
            )
        
        if 'response' not in result:
            logger.error(f"Result missing 'response' key: {result}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI service result missing response"
            )
        
        if 'chat_id' not in result:
            logger.error(f"Result missing 'chat_id' key: {result}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI service result missing chat_id"
            )
        
        return ChatResponse(
            response=result['response'],
            sources=result.get('sources', []),
            chat_id=result['chat_id']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat with documents: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing your request: {str(e)}"
        )

@router.get("/retrieve")
async def retrieve_relevant_chunks(
    paper_id: str,
    query: str,
    k: int = 8,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve top-K relevant chunks or abstracts for a paper using simple keyword scoring."""
    try:
        items = []
        # If embeddings available and API key set, use vector similarity
        api_key = os.getenv('OPENAI_API_KEY')
        use_vectors = bool(api_key)
        rows = db.query(DocumentChunk, Document).join(Document, Document.id == DocumentChunk.document_id).filter(
            Document.paper_id == paper_id
        ).all()
        if use_vectors and rows:
            client = OpenAI(api_key=api_key)
            qemb = client.embeddings.create(model="text-embedding-3-small", input=query).data[0].embedding
            def cos(a, b):
                # a,b are lists
                import numpy as _np
                try:
                    va = _np.array(a, dtype=float)
                    vb = _np.array(b, dtype=float)
                    denom = _np.linalg.norm(va) * _np.linalg.norm(vb)
                    return float(_np.dot(va, vb) / denom) if denom else 0.0
                except Exception:
                    # Fallback pure python
                    s = sum(x*y for x,y in zip(a,b))
                    na = math.sqrt(sum(x*x for x in a))
                    nb = math.sqrt(sum(y*y for y in b))
                    return (s / (na*nb)) if na and nb else 0.0
            for ch, doc in rows:
                emb = ch.embedding
                if isinstance(emb, str):
                    try:
                        import json as _json
                        emb = _json.loads(emb)
                    except Exception:
                        emb = None
                if not emb:
                    continue
                score = cos(qemb, emb)
                if score > 0:
                    items.append({ 'text': ch.chunk_text, 'chunk_index': ch.chunk_index, 'document_id': str(doc.id), 'score': score })
            if items:
                items = sorted(items, key=lambda x: x['score'], reverse=True)[:max(1, min(k, 20))]
                return { 'query': query, 'results': items, 'method': 'embedding' }

        # Fallback: keyword scoring on chunks, then abstracts
        q_terms = [t for t in query.lower().split() if len(t) > 2]
        for ch, doc in rows:
            txt = (ch.chunk_text or '').lower()
            score = sum(txt.count(t) for t in q_terms)
            if score > 0:
                items.append({ 'text': ch.chunk_text, 'chunk_index': ch.chunk_index, 'document_id': str(doc.id), 'score': score })
        if not items:
            refs = db.query(Reference).filter(Reference.paper_id == paper_id).all()
            for r in refs:
                txt = (r.abstract or '').lower()
                if not txt:
                    continue
                score = sum(txt.count(t) for t in q_terms)
                if score > 0:
                    items.append({ 'text': r.abstract, 'reference_id': str(r.id), 'score': score })
        items = sorted(items, key=lambda x: x['score'], reverse=True)[:max(1, min(k, 20))]
        return { 'query': query, 'results': items, 'method': 'keyword' }
    except Exception as e:
        logger.error(f"retrieve_relevant_chunks failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/papers/{paper_id}/embed")
async def embed_paper(
    paper_id: str,
    model: str = "text-embedding-3-small",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Compute and store embeddings for all chunks in a paper's documents."""
    try:
        count = document_processor.embed_paper_chunks(db, paper_id, model=model)
        return { 'paper_id': paper_id, 'embedded_chunks': count, 'model': model }
    except Exception as e:
        logger.error(f"Embedding for paper {paper_id} failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents/{document_id}/process", response_model=DocumentProcessingResponse)
async def process_document_for_ai(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Process a document for AI: extract text, chunk it, generate embeddings
    """
    try:
        # Get the document
        document = db.query(Document).filter(
            Document.id == document_id,
            Document.owner_id == current_user.id
        ).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Check if already processed
        if document.is_processed_for_ai:
            return DocumentProcessingResponse(
                success=True,
                message="Document already processed for AI",
                document_id=document_id
            )
        
        # Process the document
        success = document_processor.process_document_for_ai(db, document)
        
        if success:
            return DocumentProcessingResponse(
                success=True,
                message="Document successfully processed for AI",
                document_id=document_id
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to process document for AI"
            )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing document {document_id} for AI: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing the document: {str(e)}"
        )


@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get all chunks for a specific document
    """
    try:
        # Verify document ownership
        document = db.query(Document).filter(
            Document.id == document_id,
            Document.owner_id == current_user.id
        ).first()
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Get chunks
        chunks = document_processor.get_document_chunks(db, document_id)
        
        return {
            "document_id": document_id,
            "chunks": [
                {
                    "id": str(chunk.id),
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.chunk_text,  # Return full text without truncation
                    "metadata": chunk.chunk_metadata
                }
                for chunk in chunks
            ],
            "total_chunks": len(chunks)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting chunks for document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while retrieving document chunks: {str(e)}"
        )


@router.get("/chat-history")
async def get_chat_history(
    limit: int = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get user's AI chat history
    """
    try:
        chat_sessions = ai_service.get_chat_history(db, str(current_user.id), limit)
        
        return {
            "chat_sessions": [
                {
                    "id": str(session.id),
                    "query": session.query,
                    "response": session.response,  # Return full response without truncation
                    "created_at": session.created_at.isoformat(),
                    "sources_count": len(session.sources) if session.sources else 0
                }
                for session in chat_sessions
            ],
            "total_sessions": len(chat_sessions)
        }
        
    except Exception as e:
        logger.error(f"Error getting chat history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while retrieving chat history: {str(e)}"
        )


@router.get("/status")
async def get_ai_service_status():
    """
    Get OpenAI API service status and readiness
    """
    try:
        # Get detailed initialization status
        init_status = ai_service.get_initialization_status()
        
        return {
            "status": init_status["status"],
            "progress": init_status["progress"],
            "message": init_status["message"]
        }
        
    except Exception as e:
        logger.error(f"Error getting OpenAI API status: {str(e)}")
        return {
            "status": "error",
            "progress": 0,
            "message": f"Error: {str(e)}"
        }

@router.get("/models")
async def get_model_configuration():
    """
    Get current model configuration and available options
    """
    try:
        return ai_service.get_model_configuration()
    except Exception as e:
        logger.error(f"Error getting model configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving model configuration: {str(e)}"
        )

@router.put("/models")
async def update_model_configuration(
    request: ModelConfigurationRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Update model configuration
    """
    try:
        success = ai_service.update_model_configuration(
            request.provider, 
            request.embedding_model, 
            request.chat_model
        )
        if success:
            return {"message": "Model configuration updated successfully"}
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid model configuration"
            )
    except Exception as e:
        logger.error(f"Error updating model configuration: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error updating model configuration: {str(e)}"
        )


# ===== AI WRITING TOOLS ENDPOINTS =====

@router.post("/writing/generate", response_model=TextGenerationResponse)
async def generate_text(
    request: TextGenerationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Generate, expand, rephrase, or complete text using AI
    """
    try:
        logger.info(f"Text generation request from user {current_user.id}: {request.instruction}")
        
        # Check if AI service is ready
        if ai_service.initialization_status != "ready":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not ready. Please try again later."
            )
        
        # Generate text using AI service
        result = ai_service.generate_text(
            text=request.text,
            instruction=request.instruction,
            context=request.context,
            max_length=request.max_length
        )
        
        return TextGenerationResponse(
            generated_text=result['generated_text'],
            original_text=request.text,
            instruction=request.instruction,
            word_count=len(result['generated_text'].split()),
            processing_time=result.get('processing_time', 0.0)
        )
        
    except Exception as e:
        logger.error(f"Error in text generation: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while generating text: {str(e)}"
        )


@router.post("/writing/generate/stream")
async def generate_text_stream(
    request: TextGenerationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Stream text generation response in plain text chunks.
    """
    try:
        if ai_service.initialization_status != "ready":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not ready. Please try again later."
            )

        def streamer():
            yield from ai_service.stream_generate_text(
                text=request.text,
                instruction=request.instruction,
                context=request.context,
                max_length=request.max_length or 500
            )

        return StreamingResponse(streamer(), media_type="text/plain")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in text generation stream: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while generating text: {str(e)}"
        )


@router.post("/writing/grammar-check", response_model=GrammarCheckResponse)
async def check_grammar_and_style(
    request: GrammarCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Check grammar, style, and clarity of text using AI
    """
    try:
        logger.info(f"Grammar check request from user {current_user.id}")
        
        # Check if AI service is ready
        if ai_service.initialization_status != "ready":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not ready. Please try again later."
            )
        
        # Perform grammar and style check
        result = ai_service.check_grammar_and_style(
            text=request.text,
            check_grammar=request.check_grammar,
            check_style=request.check_style,
            check_clarity=request.check_clarity
        )
        
        return GrammarCheckResponse(
            corrected_text=result['corrected_text'],
            original_text=request.text,
            suggestions=result.get('suggestions', []),
            overall_score=result.get('overall_score', 0.0),
            processing_time=result.get('processing_time', 0.0)
        )
        
    except Exception as e:
        logger.error(f"Error in grammar check: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while checking grammar: {str(e)}"
        )


@router.post("/writing/research-context", response_model=ResearchContextResponse)
async def enhance_with_research_context(
    request: ResearchContextRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Enhance text using research context from user's papers
    """
    try:
        logger.info(f"Research context request from user {current_user.id}: {request.query_type}")
        
        # Check if AI service is ready
        if ai_service.initialization_status != "ready":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not ready. Please try again later."
            )
        
        # Verify user has access to the specified papers
        for paper_id in request.paper_ids:
            # Check if paper exists and user has access
            # This would need to be implemented based on your paper access model
            pass
        
        # Enhance text using research context
        result = ai_service.enhance_with_research_context(
            text=request.text,
            paper_ids=request.paper_ids,
            query_type=request.query_type,
            user_id=str(current_user.id)
        )
        
        return ResearchContextResponse(
            enhanced_text=result['enhanced_text'],
            original_text=request.text,
            suggestions=result.get('suggestions', []),
            relevant_sources=result.get('relevant_sources', []),
            processing_time=result.get('processing_time', 0.0)
        )
        
    except Exception as e:
        logger.error(f"Error in research context enhancement: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while enhancing text: {str(e)}"
        )


# ===== REFERENCE-BASED AI CHAT ENDPOINTS =====

class ReferenceChatQuery(BaseModel):
    query: str
    paper_id: Optional[str] = None  # If provided, scope to this paper's references; otherwise use global library
    max_results: Optional[int] = 8  # Maximum number of reference chunks to use
    document_excerpt: Optional[str] = None  # Optional paper draft excerpt to provide additional context

class ReferenceChatResponse(BaseModel):
    response: str
    sources: List[str]  # List of reference titles
    sources_data: List[Dict[str, Any]]  # Detailed source information
    chat_id: str
    scope: str  # "paper" or "global"
    paper_title: Optional[str] = None  # If scoped to paper

def _chunk_text_stream(text: str, chunk_size: int = 512):
    """
    Yield plain text chunks for streaming responses.
    """
    if not text:
        yield ""
        return
    for i in range(0, len(text), chunk_size):
        yield text[i:i + chunk_size]


@router.post("/chat-with-references", response_model=ReferenceChatResponse)
async def chat_with_references(
    query: ReferenceChatQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Chat with user's references using RAG (Retrieval Augmented Generation)
    Can be scoped to a specific paper's references or the entire user library
    """
    try:
        logger.info(f"Reference chat request from user {current_user.id}: {query.query}")
        
        # Check if AI service is ready
        if ai_service.initialization_status != "ready":
            logger.warning("AI service not ready")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not ready. Please try again later."
            )

        # Validate paper access if paper_id is provided
        paper_title = None
        if query.paper_id:
            from app.models.research_paper import ResearchPaper
            from app.models.paper_member import PaperMember
            
            paper = db.query(ResearchPaper).filter(ResearchPaper.id == query.paper_id).first()
            if not paper:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Research paper not found"
                )
            
            # Check if user has access to this paper
            has_access = False
            if paper.owner_id == current_user.id:
                has_access = True
            else:
                member = db.query(PaperMember).filter(
                    PaperMember.paper_id == query.paper_id,
                    PaperMember.user_id == current_user.id,
                    PaperMember.status == "accepted"
                ).first()
                if member:
                    has_access = True
            
            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to paper references"
                )
            
            paper_title = paper.title

        # Check if user has any processed references
        logger.info(f"🔍 Checking references for user ID: {current_user.id} (type: {type(current_user.id)})")
        
        if query.paper_id:
            processed_refs = db.query(Reference).join(
                PaperReference, PaperReference.reference_id == Reference.id
            ).filter(
                PaperReference.paper_id == query.paper_id,
                Reference.status == "analyzed"
            )
        else:
            processed_refs = db.query(Reference).filter(
                Reference.owner_id == current_user.id,
                Reference.status == "analyzed"
            )
        
        ref_count = processed_refs.count()
        logger.info(f"User {current_user.id} has {ref_count} processed references in scope")
        
        # Additional debugging - let's see all references for this user
        all_refs = db.query(Reference).filter(Reference.owner_id == current_user.id).all()
        logger.info(f"📚 User has {len(all_refs)} total references (any status)")
        for ref in all_refs:
            logger.info(f"  - {ref.id}: status={ref.status}, title={ref.title[:50]}...")
        
        if ref_count == 0:
            # Allow a graceful fallback: inform the user which references are missing PDFs instead of hard-blocking
            scoped_refs: List[Reference] = []
            if query.paper_id:
                scoped_refs = (
                    db.query(Reference)
                    .join(PaperReference, PaperReference.reference_id == Reference.id)
                    .filter(PaperReference.paper_id == query.paper_id)
                    .all()
                )
            else:
                scoped_refs = (
                    db.query(Reference)
                    .filter(Reference.owner_id == current_user.id)
                    .all()
                )

            if not scoped_refs:
                scope_msg = f"for paper '{paper_title}'" if query.paper_id else "in your library"
                error_msg = f"No references found {scope_msg}. Please add references with PDFs first."
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg
                )

            missing_titles = [
                (ref.title or "Untitled reference")
                for ref in scoped_refs
                if not getattr(ref, "pdf_url", None)
            ]
            pending_processing = [
                (ref.title or "Untitled reference")
                for ref in scoped_refs
                if getattr(ref, "pdf_url", None) and ref.status != "analyzed"
            ]

            if missing_titles or pending_processing:
                missing_str = ", ".join(missing_titles[:5]) + ("…" if len(missing_titles) > 5 else "")
                pending_str = ", ".join(pending_processing[:5]) + ("…" if len(pending_processing) > 5 else "")
                parts = []
                if missing_titles:
                    parts.append(f"Missing PDFs: {missing_str}.")
                if pending_processing:
                    parts.append(f"Needs processing: {pending_str}.")
                detail_msg = " ".join(parts) or "References need PDFs or processing for grounded answers."
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=detail_msg,
                )

        # Perform chat with references
        logger.info(f"Calling AI service for reference chat - user {current_user.id}")
        result = ai_service.chat_with_references(
            db, 
            str(current_user.id), 
            query.query, 
            query.paper_id,
            document_excerpt=query.document_excerpt
        )
        
        logger.info(f"AI service returned result: {result}")
        
        # Validate result format
        if not isinstance(result, dict):
            logger.error(f"AI service returned non-dict result: {type(result)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AI service returned invalid result format"
            )
        
        required_keys = ['response', 'sources', 'sources_data', 'chat_id']
        for key in required_keys:
            if key not in result:
                logger.error(f"Result missing '{key}' key: {result}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"AI service result missing {key}"
        )

        return ReferenceChatResponse(
            response=result['response'],
            sources=result['sources'],
            sources_data=result['sources_data'],
            chat_id=result['chat_id'],
            scope="paper" if query.paper_id else "global",
            paper_title=paper_title
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat with references: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing your request: {str(e)}"
        )


@router.post("/chat-with-references/stream")
async def chat_with_references_stream(
    query: ReferenceChatQuery,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Stream reference chat response in plain text chunks.
    """
    try:
        # Check if AI service is ready
        if ai_service.initialization_status != "ready":
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI service is not ready. Please try again later."
            )

        paper_title = None
        if query.paper_id:
            from app.models.research_paper import ResearchPaper
            from app.models.paper_member import PaperMember

            paper = db.query(ResearchPaper).filter(ResearchPaper.id == query.paper_id).first()
            if not paper:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Research paper not found"
                )

            has_access = paper.owner_id == current_user.id
            if not has_access:
                member = db.query(PaperMember).filter(
                    PaperMember.paper_id == query.paper_id,
                    PaperMember.user_id == current_user.id,
                    PaperMember.status == "accepted"
                ).first()
                has_access = bool(member)

            if not has_access:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied to paper references"
                )

            paper_title = paper.title

        # Check processed references (paper scoped ignores owner)
        if query.paper_id:
            processed_refs = db.query(Reference).join(
                PaperReference, PaperReference.reference_id == Reference.id
            ).filter(
                PaperReference.paper_id == query.paper_id,
                Reference.status == "analyzed"
            )
        else:
            processed_refs = db.query(Reference).filter(
                Reference.owner_id == current_user.id,
                Reference.status == "analyzed"
            )
        ref_count = processed_refs.count()
        if ref_count == 0 and not query.document_excerpt:
            if query.paper_id:
                scoped_refs = db.query(Reference).join(
                    PaperReference, PaperReference.reference_id == Reference.id
                ).filter(PaperReference.paper_id == query.paper_id).all()
            else:
                scoped_refs = db.query(Reference).filter(Reference.owner_id == current_user.id).all()

            if not scoped_refs:
                scope_msg = f"for paper '{paper_title}'" if query.paper_id else "in your library"
                error_msg = f"No references found {scope_msg}. Please add references with PDFs first."
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=error_msg
                )

            missing_titles = [
                (ref.title or "Untitled reference")
                for ref in scoped_refs
                if not getattr(ref, "pdf_url", None)
            ]
            pending_processing = [
                (ref.title or "Untitled reference")
                for ref in scoped_refs
                if getattr(ref, "pdf_url", None) and ref.status != "analyzed"
            ]

            parts = []
            if missing_titles:
                notice_list = ", ".join(missing_titles[:5]) + ("…" if len(missing_titles) > 5 else "")
                parts.append(f"Missing PDFs: {notice_list}.")
            if pending_processing:
                pending_str = ", ".join(pending_processing[:5]) + ("…" if len(pending_processing) > 5 else "")
                parts.append(f"Needs processing: {pending_str}.")
            detail_msg = " ".join(parts) or "References need PDFs or processing for grounded answers."
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=detail_msg,
            )

        # Get relevant reference chunks (optional if document excerpt provided)
        logger.info("🔍 Getting relevant reference chunks (stream)...")
        chunks = ai_service.get_relevant_reference_chunks(
            db, query.query, str(current_user.id), query.paper_id, limit=query.max_results or 8
        )
        # Let downstream handle empty chunks when doc excerpt is provided

        def streamer():
            yield from ai_service.stream_reference_rag_response(
                query.query,
                chunks,
                document_excerpt=query.document_excerpt,
                paper_id=query.paper_id,
                user_id=str(current_user.id),
                db=db,
            )

        return StreamingResponse(streamer(), media_type="text/plain")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in chat_with_references_stream: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing your request: {str(e)}"
        )


@router.post("/papers/{paper_id}/ingest-references")
async def ingest_paper_references(
    paper_id: str,
    force_reprocess: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ingest all references for a specific paper (download PDFs and process for AI)
    """
    try:
        # Validate paper access
        from app.models.research_paper import ResearchPaper
        from app.models.paper_member import PaperMember
        
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
        if not paper:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Research paper not found"
            )
        
        # Check if user has access to this paper
        has_access = False
        if paper.owner_id == current_user.id:
            has_access = True
        else:
            member = db.query(PaperMember).filter(
                PaperMember.paper_id == paper_id,
                PaperMember.user_id == current_user.id,
                PaperMember.status == "accepted"
            ).first()
            if member:
                has_access = True
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to paper"
            )

        # Use existing analyze_reference_task for all paper references
        references = db.query(Reference).filter(Reference.paper_id == paper_id).all()
        
        if not references:
            return {
                "success": True,
                "message": "No references found for this paper",
                "total_references": 0,
                "processed": 0,
                "failed": 0,
                "skipped": 0
            }

        # Filter out already processed references unless forcing reprocess
        refs_to_process = []
        if force_reprocess:
            refs_to_process = references
        else:
            refs_to_process = [ref for ref in references if ref.status in ("pending", "failed")]

        if not refs_to_process:
            return {
                "success": True,
                "message": "All references already processed",
                "total_references": len(references),
                "processed": 0,
                "failed": 0,
                "skipped": len(references)
            }

        # Process references using existing system
        processed = 0
        failed = 0
        
        from app.api.v1.research_papers import analyze_reference_task
        
        for ref in refs_to_process:
            try:
                analyze_reference_task(str(ref.id))
                processed += 1
            except Exception as e:
                logger.error(f"Failed to process reference {ref.id}: {str(e)}")
                failed += 1

        result = {
            "success": True,
            "message": f"Processed {processed} references successfully",
            "total_references": len(references),
            "processed": processed,
            "failed": failed,
            "skipped": len(references) - len(refs_to_process)
        }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting paper references: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error ingesting references: {str(e)}"
        )


@router.post("/references/{reference_id}/ingest")
async def ingest_single_reference(
    reference_id: str,
    force_reprocess: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ingest a single reference (download PDF and process for AI)
    """
    try:
        # Validate reference ownership
        reference = db.query(Reference).filter(
            Reference.id == reference_id,
            Reference.owner_id == current_user.id
        ).first()
        
        if not reference:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reference not found"
            )

        # Use existing analyze_reference_task
        try:
            from app.api.v1.research_papers import analyze_reference_task
            analyze_reference_task(reference_id)
            
            # Refresh reference to get updated status
            db.refresh(reference)
            
            result = {
                "success": reference.status == "analyzed",
                "message": f"Reference processed successfully" if reference.status == "analyzed" else "Processing completed with issues",
                "status": reference.status,
                "reference_id": reference_id
            }
        except Exception as e:
            result = {
                "success": False,
                "error": f"Processing failed: {str(e)}",
                "reference_id": reference_id
            }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error ingesting reference: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error ingesting reference: {str(e)}"
        )


@router.get("/references/{reference_id}/chat-status")
async def get_reference_chat_status(
    reference_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the chat readiness status of a reference
    """
    try:
        reference = db.query(Reference).filter(
            Reference.id == reference_id,
            Reference.owner_id == current_user.id
        ).first()
        
        if not reference:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Reference not found"
            )

        # Check if reference has processed chunks
        if reference.status == "analyzed" and reference.document_id:
            from app.models.document_chunk import DocumentChunk
            
            chunk_count = db.query(DocumentChunk).filter(
                DocumentChunk.reference_id == reference_id
            ).count()
            
            return {
                "reference_id": reference_id,
                "chat_ready": chunk_count > 0,
                "status": reference.status,
                "chunk_count": chunk_count,
                "has_pdf": bool(reference.pdf_url),
                "pdf_url": reference.pdf_url if reference.pdf_url and not reference.pdf_url.startswith("http") else None
            }
        else:
            return {
                "reference_id": reference_id,
                "chat_ready": False,
                "status": reference.status,
                "chunk_count": 0,
                "has_pdf": bool(reference.pdf_url),
                "pdf_url": None
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting reference chat status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting chat status: {str(e)}"
        )


@router.get("/papers/{paper_id}/references/chat-status")
async def get_paper_references_chat_status(
    paper_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get the chat readiness status of all references for a paper
    """
    try:
        # Validate paper access
        from app.models.research_paper import ResearchPaper
        from app.models.paper_member import PaperMember
        
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == paper_id).first()
        if not paper:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Research paper not found"
            )
        
        # Check if user has access to this paper
        has_access = False
        if paper.owner_id == current_user.id:
            has_access = True
        else:
            member = db.query(PaperMember).filter(
                PaperMember.paper_id == paper_id,
                PaperMember.user_id == current_user.id,
                PaperMember.status == "accepted"
            ).first()
            if member:
                has_access = True
        
        if not has_access:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied to paper"
            )

        # Get all references for this paper
        references = db.query(Reference).filter(Reference.paper_id == paper_id).all()
        
        # Get chunk counts for analyzed references
        from app.models.document_chunk import DocumentChunk
        
        total_refs = len(references)
        chat_ready_refs = 0
        total_chunks = 0
        
        ref_statuses = []
        
        for ref in references:
            chunk_count = 0
            if ref.status == "analyzed" and ref.document_id:
                chunk_count = db.query(DocumentChunk).filter(
                    DocumentChunk.reference_id == str(ref.id)
                ).count()
                total_chunks += chunk_count
                if chunk_count > 0:
                    chat_ready_refs += 1
            
            ref_statuses.append({
                "id": str(ref.id),
                "title": ref.title,
                "status": ref.status,
                "chunk_count": chunk_count,
                "has_pdf": bool(ref.pdf_url),
                "chat_ready": chunk_count > 0
            })

        return {
            "paper_id": paper_id,
            "paper_title": paper.title,
            "total_references": total_refs,
            "chat_ready_references": chat_ready_refs,
            "total_chunks": total_chunks,
            "overall_chat_ready": chat_ready_refs > 0,
            "references": ref_statuses
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting paper references chat status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error getting chat status: {str(e)}"
        )


# AI Text Tools Models
class TextToolsRequest(BaseModel):
    text: str
    action: str  # 'paraphrase', 'tone', 'summarize', 'explain', 'synonyms'
    tone: Optional[str] = None  # For tone action: 'formal', 'casual', 'academic', 'friendly', 'professional'
    project_id: Optional[str] = None  # Project ID to use project's configured model


class TextToolsResponse(BaseModel):
    result: str


def _is_valid_uuid_str(val: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        from uuid import UUID as _UUID
        _UUID(str(val))
        return True
    except (ValueError, AttributeError):
        return False


def _parse_project_short_id(url_id: str) -> str | None:
    """Extract short_id from a URL identifier (slug-shortid or just shortid)."""
    if not url_id or _is_valid_uuid_str(url_id):
        return None
    if len(url_id) == 8 and url_id.isalnum():
        return url_id
    last_hyphen = url_id.rfind('-')
    if last_hyphen > 0:
        potential = url_id[last_hyphen + 1:]
        if len(potential) == 8 and potential.isalnum():
            return potential
    return None


@router.post("/text-tools", response_model=TextToolsResponse)
async def ai_text_tools(
    request: TextToolsRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    AI-powered text manipulation tools: paraphrase, tone change, summarize, explain, find synonyms.
    Uses the project's configured model via OpenRouter if project_id is provided.
    """
    try:
        logger.info(f"AI text tools request from user {current_user.id}: action={request.action}")

        # Import here to avoid circular imports
        from app.models import Project
        from app.api.utils.openrouter_access import resolve_openrouter_key_for_project, resolve_openrouter_key_for_user
        from uuid import UUID as _UUID

        # Default model
        model = "openai/gpt-4o-mini"

        # Get project settings if project_id provided
        project = None
        use_owner_key_for_team = False
        if request.project_id:
            # Try UUID lookup first
            if _is_valid_uuid_str(request.project_id):
                try:
                    uuid_val = _UUID(request.project_id)
                    project = db.query(Project).filter(Project.id == uuid_val).first()
                except (ValueError, AttributeError):
                    pass

            # Try short_id lookup if UUID lookup failed
            if not project:
                short_id = _parse_project_short_id(request.project_id)
                if short_id:
                    project = db.query(Project).filter(Project.short_id == short_id).first()

            if project:
                discussion_settings = project.discussion_settings or {}
                model = discussion_settings.get("model", "openai/gpt-5.2-20251211")
                use_owner_key_for_team = discussion_settings.get("use_owner_key_for_team", False)

        # Resolve OpenRouter API key
        if project:
            key_result = resolve_openrouter_key_for_project(
                db, current_user, project, use_owner_key_for_team=use_owner_key_for_team
            )
        else:
            key_result = resolve_openrouter_key_for_user(db, current_user)

        api_key = key_result.get("api_key")
        if not api_key:
            error_detail = key_result.get("error_detail", "No API key available")
            error_status = key_result.get("error_status", 402)
            raise HTTPException(status_code=error_status, detail=error_detail)

        # Build prompt based on action
        if request.action == "paraphrase":
            prompt = f"Paraphrase the following text while maintaining its meaning. Return ONLY the paraphrased text, no explanations:\n\n{request.text}"
        elif request.action == "tone":
            tone = request.tone or "formal"
            prompt = f"Rewrite the following text in a {tone} tone. Return ONLY the rewritten text, no explanations:\n\n{request.text}"
        elif request.action == "summarize":
            prompt = f"Provide a concise summary of the following text. Return ONLY the summary, no explanations:\n\n{request.text}"
        elif request.action == "explain":
            prompt = f"Explain the meaning and key concepts in the following text clearly and concisely:\n\n{request.text}"
        elif request.action == "synonyms":
            prompt = f"Provide synonyms and alternative phrasings for key terms in the following text. Format as a brief list:\n\n{request.text}"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid action: {request.action}"
            )

        # Create OpenRouter client with timeout
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://scholarhub.space",
                "X-Title": "ScholarHub",
            },
            timeout=30.0,  # 30 second timeout
        )

        # Call OpenRouter API with selected model (project-configured if provided)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are a helpful writing assistant for academic and professional writing. Provide clear, concise, and accurate responses. Follow instructions exactly."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=1000
        )

        result = (response.choices[0].message.content or "").strip()

        return TextToolsResponse(result=result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in AI text tools: {str(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while processing your request: {str(e)}"
        )
