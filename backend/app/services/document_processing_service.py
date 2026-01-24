import os
import re
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.ai_service import AIService
from openai import OpenAI
import json
import logging

logger = logging.getLogger(__name__)


class DocumentProcessingService:
    def __init__(self):
        self.ai_service = AIService()
        self.chunk_size = 2000  # Increased chunk size to reduce fragmentation
        self.chunk_overlap = 300  # Increased overlap to preserve context
        
        # Check if OpenAI API is available
        if self.ai_service.initialization_status != "ready":
            logger.warning("OpenAI API not ready, document processing may fail")

    def process_document_for_ai(self, db: Session, document: Document) -> bool:
        """
        Process a document for AI: extract text, chunk it, and store chunks (no embeddings)
        """
        try:
            logger.info(f"Processing document {document.id} for AI")
            
            # Check if document is already processed
            if document.is_processed_for_ai:
                logger.info(f"Document {document.id} already processed for AI")
                return True
            
            # Extract text from document
            text = self.extract_text_from_document(document)
            if not text:
                logger.error(f"Failed to extract text from document {document.id}")
                return False
            
            # Chunk the text
            chunks = self.chunk_document(text)
            logger.info(f"Created {len(chunks)} chunks for document {document.id}")
            
            # Store chunks
            self.store_document_chunks(db, document.id, chunks)

            # Update document status
            document.is_processed_for_ai = True
            document.processed_at = func.now()
            db.commit()

            # Auto-embed chunks for RAG (if API key configured)
            try:
                self.embed_document_chunks(db, str(document.id))
            except Exception as e:
                logger.warning(f"Embedding skipped/failed for document {document.id}: {e}")
            
            logger.info(f"Successfully processed document {document.id} for AI (no embeddings)")
            return True
            
        except Exception as e:
            logger.error(f"Error processing document {document.id} for AI: {str(e)}")
            db.rollback()
            return False

    def extract_text_from_document(self, document: Document) -> str:
        """
        Extract text from document based on its type
        """
        try:
            if document.extracted_text:
                # Sanitize: remove NUL characters that cause PostgreSQL errors
                return (document.extracted_text or '').replace('\x00', '')

            # If no extracted text, try to extract from file
            if document.document_type.value == 'pdf':
                text = self._extract_text_from_pdf(document.file_path)
            elif document.document_type.value == 'docx':
                text = self._extract_text_from_docx(document.file_path)
            elif document.document_type.value == 'txt':
                text = self._extract_text_from_txt(document.file_path)
            else:
                logger.warning(f"Unsupported document type: {document.document_type}")
                return ""

            # Sanitize: remove NUL characters that cause PostgreSQL errors
            return (text or '').replace('\x00', '')

        except Exception as e:
            logger.error(f"Error extracting text from document {document.id}: {str(e)}")
            return ""

    def _extract_text_from_pdf(self, file_path: str) -> str:
        """Extract text from PDF file"""
        try:
            import PyPDF2
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except Exception as e:
            logger.error(f"Error extracting text from PDF {file_path}: {str(e)}")
            return ""

    def _extract_text_from_docx(self, file_path: str) -> str:
        """Extract text from DOCX file"""
        try:
            from docx import Document
            doc = Document(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            logger.error(f"Error extracting text from DOCX {file_path}: {str(e)}")
            return ""

    def _extract_text_from_txt(self, file_path: str) -> str:
        """Extract text from TXT file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read().strip()
        except Exception as e:
            logger.error(f"Error extracting text from TXT {file_path}: {str(e)}")
            return ""

    def chunk_document(self, text: str) -> List[Dict[str, Any]]:
        """
        Split document text into overlapping chunks while preserving semantic coherence
        """
        chunks = []
        
        # Clean and normalize text
        text = re.sub(r'\s+', ' ', text).strip()
        
        if len(text) <= self.chunk_size:
            chunks.append({
                'text': text,
                'index': 0,
                'metadata': {'start_char': 0, 'end_char': len(text)}
            })
            return chunks
        
        # Split into chunks with overlap
        start = 0
        chunk_index = 0
        
        while start < len(text):
            end = start + self.chunk_size
            
            # Try to break at sentence boundaries first
            if end < len(text):
                # Look for sentence endings within the last 200 characters
                search_start = max(start + self.chunk_size - 200, start)
                sentence_end = text.rfind('.', search_start, end)
                if sentence_end > start + self.chunk_size * 0.6:  # More flexible sentence boundary
                    end = sentence_end + 1
            
            # If no good sentence boundary, try to break at word boundaries
            if end < len(text):
                # Look for word boundaries within the last 100 characters
                search_start = max(start + self.chunk_size - 100, start)
                word_boundary = text.rfind(' ', search_start, end)
                if word_boundary > start + self.chunk_size * 0.8:  # Only break if we find a good word boundary
                    end = word_boundary
            
            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({
                    'text': chunk_text,
                    'index': chunk_index,
                    'metadata': {
                        'start_char': start,
                        'end_char': end,
                        'length': len(chunk_text)
                    }
                })
                chunk_index += 1
            
            # Move start position with overlap
            start = end - self.chunk_overlap
            if start >= len(text):
                break
        
        return chunks

    def store_document_chunks(self, db: Session, document_id: str, chunks: List[Dict[str, Any]]):
        """
        Store document chunks with their embeddings in the database
        """
        try:
            # Delete existing chunks for this document
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
            
            # Create new chunks
            for i, chunk in enumerate(chunks):
                # Sanitize chunk text: remove NUL characters that cause PostgreSQL errors
                chunk_text = chunk['text'].replace('\x00', '') if chunk['text'] else ''
                db_chunk = DocumentChunk(
                    document_id=document_id,
                    chunk_text=chunk_text,
                    chunk_index=chunk['index'],
                    chunk_metadata=chunk['metadata']
                )
                db.add(db_chunk)
            
            db.commit()
            logger.info(f"Stored {len(chunks)} chunks for document {document_id}")
            
        except Exception as e:
            logger.error(f"Error storing chunks for document {document_id}: {str(e)}")
            db.rollback()
            raise

    def get_document_chunks(self, db: Session, document_id: str) -> List[DocumentChunk]:
        """
        Retrieve all chunks for a specific document
        """
        return db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index).all()

    def delete_document_chunks(self, db: Session, document_id: str):
        """
        Delete all chunks for a specific document
        """
        try:
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
            db.commit()
            logger.info(f"Deleted chunks for document {document_id}")
        except Exception as e:
            logger.error(f"Error deleting chunks for document {document_id}: {str(e)}")
            db.rollback()
            raise

    # --- Embeddings (RAG) ---
    def embed_document_chunks(self, db: Session, document_id: str, model: str = "text-embedding-3-small", batch_size: int = 64) -> int:
        """Compute embeddings for a document's chunks using OpenAI."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set; skipping embeddings")
            return 0
        client = OpenAI(api_key=api_key)
        chunks = self.get_document_chunks(db, document_id)
        if not chunks:
            return 0
        # Sanitize text: remove NUL characters that can cause issues
        texts = [(c.chunk_text or "").replace('\x00', '')[:8000] for c in chunks]
        updated = 0
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i+batch_size]
            idxs = range(i, min(i+batch_size, len(texts)))
            try:
                resp = client.embeddings.create(model=model, input=batch)
                vectors = [d.embedding for d in resp.data]
                for j, vec in zip(idxs, vectors):
                    try:
                        chunks[j].embedding = vec
                    except Exception:
                        chunks[j].embedding = json.dumps(vec)
                    updated += 1
                db.commit()
            except Exception as e:
                logger.error(f"Embedding batch failed for document {document_id}: {e}")
        return updated

    def embed_paper_chunks(self, db: Session, paper_id: str, model: str = "text-embedding-3-small") -> int:
        from app.models.document import Document
        docs = db.query(Document).filter(Document.paper_id == paper_id).all()
        total = 0
        for d in docs:
            total += self.embed_document_chunks(db, str(d.id), model=model)
        return total
