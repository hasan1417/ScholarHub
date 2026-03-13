"""
Document Processing Service - Enhanced PDF extraction for academic papers.

Uses pymupdf4llm for high-quality PDF extraction with pdfplumber fallback.
Both Discussion AI OR and LaTeX Editor AI OR use this for RAG.
"""
import os
import re
import uuid
import json
import logging
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from pathlib import Path

from sqlalchemy.orm import Session
from sqlalchemy import func
from openai import OpenAI

from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.services.ai_service import AIService
from app.core.config import settings

logger = logging.getLogger(__name__)


def _score_extraction_quality(text: str, page_count: int) -> float:
    """Score extracted text quality from 0.0 (garbage) to 1.0 (clean)."""
    if not text or not text.strip():
        return 0.0

    score = 1.0

    # 1. Replacement/control character ratio
    bad_chars = sum(1 for c in text if c in '\ufffd\x00' or (ord(c) < 32 and c not in '\n\r\t'))
    if len(text) > 0:
        bad_ratio = bad_chars / len(text)
        if bad_ratio > 0.15:
            score -= 0.5
        elif bad_ratio > 0.05:
            score -= 0.3

    # 2. Word density per page
    words = len(text.split())
    pages = max(page_count, 1)
    words_per_page = words / pages
    if words_per_page < 30:
        score -= 0.4
    elif words_per_page < 50:
        score -= 0.2

    # 3. Structure check — expect headings in longer docs
    if pages > 5 and '#' not in text:
        score -= 0.1

    return max(0.0, min(1.0, score))


class DocumentProcessingService:
    """
    Enhanced document processing with:
    - pymupdf4llm for high-quality PDF extraction (markdown, structure)
    - pdfplumber as fallback for simpler extraction
    - PyMuPDF for image extraction
    - Smart chunking that preserves tables
    """

    def __init__(self):
        self.ai_service = AIService()
        self.chunk_size = 2000
        self.chunk_overlap = 300

        # Directory for extracted images
        self.images_dir = Path(os.getenv("UPLOADS_DIR", "uploads")) / "extracted_images"
        self.images_dir.mkdir(parents=True, exist_ok=True)

        if self.ai_service.initialization_status != "ready":
            logger.warning("OpenAI API not ready, document processing may fail")

    def process_document_for_ai(self, db: Session, document: Document) -> bool:
        """
        Process a document for AI: extract text/tables/images, chunk, and store.
        """
        try:
            logger.info(f"Processing document {document.id} for AI")

            if document.is_processed_for_ai:
                logger.info(f"Document {document.id} already processed for AI")
                return True

            # Enhanced extraction based on document type
            if document.document_type.value == 'pdf':
                extraction_result = self._extract_from_pdf_enhanced(document)
            else:
                # Fallback to basic text extraction for non-PDFs
                text = self.extract_text_from_document(document)
                extraction_result = {
                    'text': text,
                    'tables': [],
                    'images': []
                }

            if not extraction_result['text'] and not extraction_result['tables']:
                logger.error(f"Failed to extract content from document {document.id}")
                return False

            # Create chunks (text + tables as separate chunks)
            chunks = self._create_enhanced_chunks(extraction_result)
            logger.info(f"Created {len(chunks)} chunks for document {document.id} "
                       f"(tables: {len(extraction_result['tables'])}, images: {len(extraction_result['images'])})")

            # Store chunks
            self.store_document_chunks(db, document.id, chunks)

            # Update document status
            document.is_processed_for_ai = True
            document.processed_at = func.now()
            db.commit()

            # Auto-embed chunks for RAG
            try:
                self.embed_document_chunks(db, str(document.id))
            except Exception as e:
                logger.warning(f"Embedding skipped/failed for document {document.id}: {e}")

            logger.info(f"Successfully processed document {document.id}")
            return True

        except Exception as e:
            logger.error(f"Error processing document {document.id}: {str(e)}")
            db.rollback()
            return False

    def _extract_from_pdf_enhanced(self, document: Document) -> Dict[str, Any]:
        """
        Enhanced PDF extraction using pymupdf4llm (primary) or pdfplumber (fallback).
        pymupdf4llm provides:
        - Clean markdown output with headings
        - Better structure preservation
        - Links and formatting preserved
        - Good for RAG pipelines
        """
        result = {
            'text': '',
            'tables': [],
            'images': []
        }

        file_path = document.file_path
        if not file_path or not os.path.exists(file_path):
            logger.error(f"PDF file not found: {file_path}")
            return result

        # Get page count for quality scoring
        page_count = document.page_count or 0
        if not page_count:
            try:
                import fitz
                with fitz.open(file_path) as doc:
                    page_count = len(doc)
            except Exception:
                page_count = 1

        # Try pymupdf4llm first (best quality markdown for RAG)
        extraction_success = False
        try:
            import pymupdf4llm
            logger.info(f"Extracting PDF with pymupdf4llm: {file_path}")
            markdown_text = pymupdf4llm.to_markdown(file_path)

            if markdown_text and len(markdown_text) > 100:
                result['text'] = markdown_text
                extraction_success = True
                logger.info(f"pymupdf4llm extracted {len(markdown_text)} chars from {file_path}")

                # Extract tables from markdown
                result['tables'] = self._extract_tables_from_markdown(markdown_text)
            else:
                logger.warning(f"pymupdf4llm returned insufficient content, falling back to pdfplumber")
        except ImportError:
            logger.warning("pymupdf4llm not installed, falling back to pdfplumber")
        except Exception as e:
            logger.warning(f"pymupdf4llm extraction failed: {e}, falling back to pdfplumber")

        # Fallback to pdfplumber if pymupdf4llm failed
        if not extraction_success:
            result = self._extract_with_pdfplumber(file_path)

        # Extract images with PyMuPDF (regardless of text extraction method)
        result['images'] = self._extract_images_pymupdf(file_path, document.id)

        # Sanitize text
        result['text'] = (result['text'] or '').replace('\x00', '')

        # Score extraction quality; try Mistral OCR fallback for low-quality extractions
        quality_score = _score_extraction_quality(result['text'], page_count)
        if quality_score < 0.7 and settings.MISTRAL_API_KEY:
            logger.info(f"Low extraction quality ({quality_score:.2f}) for {file_path}, trying Mistral OCR")
            try:
                from app.services.mistral_ocr_service import extract_with_mistral_ocr_sync
                mistral_text = extract_with_mistral_ocr_sync(file_path, settings.MISTRAL_API_KEY)
                if mistral_text:
                    mistral_score = _score_extraction_quality(mistral_text, page_count)
                    if mistral_score > quality_score:
                        logger.info("Mistral OCR improved extraction for %s (%.2f -> %.2f)", file_path, quality_score, mistral_score)
                        result['text'] = mistral_text
                        result['tables'] = self._extract_tables_from_markdown(mistral_text)
                        quality_score = mistral_score
            except Exception as e:
                logger.warning(f"Mistral OCR fallback failed for {file_path}: {e}")

        document.extraction_quality = quality_score

        return result

    def _extract_tables_from_markdown(self, markdown_text: str) -> List[Dict]:
        """Extract table metadata from markdown output."""
        tables = []
        # Find markdown tables (lines starting with |)
        lines = markdown_text.split('\n')
        table_start = None
        current_table_lines = []

        for i, line in enumerate(lines):
            if line.strip().startswith('|') and '|' in line[1:]:
                if table_start is None:
                    table_start = i
                current_table_lines.append(line)
            else:
                if current_table_lines and len(current_table_lines) >= 2:
                    # Valid table found
                    tables.append({
                        'page': 0,
                        'index': len(tables),
                        'markdown': '\n'.join(current_table_lines),
                        'rows': len(current_table_lines) - 1,  # Minus header separator
                        'cols': current_table_lines[0].count('|') - 1
                    })
                table_start = None
                current_table_lines = []

        # Don't forget last table
        if current_table_lines and len(current_table_lines) >= 2:
            tables.append({
                'page': 0,
                'index': len(tables),
                'markdown': '\n'.join(current_table_lines),
                'rows': len(current_table_lines) - 1,
                'cols': current_table_lines[0].count('|') - 1
            })

        return tables

    def _extract_with_pdfplumber(self, file_path: str) -> Dict[str, Any]:
        """Fallback extraction using pdfplumber."""
        result = {
            'text': '',
            'tables': [],
            'images': []
        }

        try:
            import pdfplumber

            text_parts = []
            tables_found = []

            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    page_text = page.extract_text() or ""
                    if page_text:
                        text_parts.append(f"[Page {page_num}]\n{page_text}")

                    page_tables = page.extract_tables()
                    for table_idx, table in enumerate(page_tables):
                        if table and len(table) > 1:
                            markdown_table = self._table_to_markdown(table)
                            if markdown_table:
                                tables_found.append({
                                    'page': page_num,
                                    'index': table_idx,
                                    'markdown': markdown_table,
                                    'rows': len(table),
                                    'cols': len(table[0]) if table else 0
                                })

            result['text'] = '\n\n'.join(text_parts)
            result['tables'] = tables_found
            logger.info(f"pdfplumber extracted {len(text_parts)} pages, {len(tables_found)} tables")

        except ImportError:
            logger.warning("pdfplumber not available, falling back to PyPDF2")
            result['text'] = self._extract_text_from_pdf_legacy(file_path)
        except Exception as e:
            logger.error(f"pdfplumber extraction failed: {e}, falling back to PyPDF2")
            result['text'] = self._extract_text_from_pdf_legacy(file_path)

        return result

    def _extract_images_pymupdf(self, file_path: str, document_id) -> List[Dict]:
        """Extract images from PDF using PyMuPDF."""
        images_extracted = []

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(file_path)

            for page_num in range(len(doc)):
                page = doc[page_num]
                image_list = page.get_images()

                for img_idx, img in enumerate(image_list):
                    try:
                        xref = img[0]
                        base_image = doc.extract_image(xref)

                        if base_image:
                            image_bytes = base_image["image"]
                            image_ext = base_image["ext"]

                            # Only save reasonably sized images (likely figures, not icons)
                            if len(image_bytes) > 5000:  # > 5KB
                                image_filename = f"{document_id}_p{page_num + 1}_img{img_idx}.{image_ext}"
                                image_path = self.images_dir / image_filename

                                with open(image_path, "wb") as img_file:
                                    img_file.write(image_bytes)

                                images_extracted.append({
                                    'page': page_num + 1,
                                    'index': img_idx,
                                    'path': str(image_path),
                                    'filename': image_filename,
                                    'size_bytes': len(image_bytes),
                                    'format': image_ext
                                })
                    except Exception as img_err:
                        logger.debug(f"Could not extract image {img_idx} from page {page_num}: {img_err}")

            doc.close()
            logger.info(f"PyMuPDF extracted {len(images_extracted)} images")

        except ImportError:
            logger.warning("PyMuPDF not available, skipping image extraction")
        except Exception as e:
            logger.warning(f"Image extraction failed: {e}")

        return images_extracted

    def _table_to_markdown(self, table: List[List[Any]]) -> Optional[str]:
        """Convert a table (list of rows) to markdown format."""
        if not table or len(table) < 2:
            return None

        try:
            # Clean cells
            def clean_cell(cell):
                if cell is None:
                    return ""
                return str(cell).replace('\n', ' ').replace('|', '\\|').strip()

            # Header row
            header = [clean_cell(c) for c in table[0]]
            if not any(header):  # Skip if header is empty
                return None

            lines = []
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * len(header)) + " |")

            # Data rows
            for row in table[1:]:
                cells = [clean_cell(c) for c in row]
                # Pad or truncate to match header length
                while len(cells) < len(header):
                    cells.append("")
                cells = cells[:len(header)]
                lines.append("| " + " | ".join(cells) + " |")

            return "\n".join(lines)

        except Exception as e:
            logger.debug(f"Table to markdown failed: {e}")
            return None

    def _create_enhanced_chunks(self, extraction_result: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create chunks from extracted content.
        - Tables are kept as single chunks (not split)
        - Images are referenced in metadata
        - Text is chunked normally
        """
        chunks = []
        chunk_index = 0

        # First, add table chunks (these shouldn't be split)
        for table in extraction_result.get('tables', []):
            markdown = table.get('markdown', '')
            if markdown and len(markdown) > 50:  # Skip tiny tables
                chunks.append({
                    'text': f"[TABLE from page {table['page']}]\n{markdown}",
                    'index': chunk_index,
                    'metadata': {
                        'type': 'table',
                        'page': table['page'],
                        'rows': table.get('rows', 0),
                        'cols': table.get('cols', 0)
                    }
                })
                chunk_index += 1

        # Add image reference chunks (so RAG knows images exist)
        images = extraction_result.get('images', [])
        if images:
            # Group images by page for a summary chunk
            image_summary = "[FIGURES/IMAGES IN DOCUMENT]\n"
            for img in images:
                image_summary += f"- Page {img['page']}: Image {img['index'] + 1} ({img['format']}, {img['size_bytes'] // 1024}KB) - Path: {img['filename']}\n"

            chunks.append({
                'text': image_summary,
                'index': chunk_index,
                'metadata': {
                    'type': 'image_index',
                    'image_count': len(images),
                    'images': [{'page': img['page'], 'path': img['path'], 'filename': img['filename']} for img in images]
                }
            })
            chunk_index += 1

        # Now chunk the regular text
        text = extraction_result.get('text', '')
        if text:
            text_chunks = self.chunk_document(text)
            for tc in text_chunks:
                tc['index'] = chunk_index
                tc['metadata']['type'] = 'text'
                chunks.append(tc)
                chunk_index += 1

        return chunks

    def _extract_text_from_pdf_legacy(self, file_path: str) -> str:
        """Legacy PDF text extraction using PyPDF2."""
        try:
            import PyPDF2
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text = ""
                for page in pdf_reader.pages:
                    text += page.extract_text() + "\n"
                return text.strip()
        except Exception as e:
            logger.error(f"PyPDF2 extraction failed for {file_path}: {e}")
            return ""

    def extract_text_from_document(self, document: Document) -> str:
        """Extract text from document based on its type."""
        try:
            if document.extracted_text:
                return (document.extracted_text or '').replace('\x00', '')

            if document.document_type.value == 'pdf':
                # Try pdfplumber first, fallback to PyPDF2
                text = self._extract_text_pdfplumber(document.file_path)
                if not text:
                    text = self._extract_text_from_pdf_legacy(document.file_path)
            elif document.document_type.value == 'docx':
                text = self._extract_text_from_docx(document.file_path)
            elif document.document_type.value == 'txt':
                text = self._extract_text_from_txt(document.file_path)
            else:
                logger.warning(f"Unsupported document type: {document.document_type}")
                return ""

            return (text or '').replace('\x00', '')

        except Exception as e:
            logger.error(f"Error extracting text from document {document.id}: {str(e)}")
            return ""

    def _extract_text_pdfplumber(self, file_path: str) -> str:
        """Extract text using pdfplumber."""
        try:
            import pdfplumber
            text_parts = []
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text_parts.append(page_text)
            return '\n\n'.join(text_parts)
        except Exception as e:
            logger.debug(f"pdfplumber extraction failed: {e}")
            return ""

    def _extract_text_from_docx(self, file_path: str) -> str:
        """Extract text from DOCX file."""
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
        """Extract text from TXT file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read().strip()
        except Exception as e:
            logger.error(f"Error extracting text from TXT {file_path}: {str(e)}")
            return ""

    def chunk_document(self, text: str) -> List[Dict[str, Any]]:
        """Split document text into overlapping chunks."""
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

        start = 0
        chunk_index = 0

        while start < len(text):
            end = start + self.chunk_size

            # Try to break at sentence boundaries
            if end < len(text):
                search_start = max(start + self.chunk_size - 200, start)
                sentence_end = text.rfind('.', search_start, end)
                if sentence_end > start + self.chunk_size * 0.6:
                    end = sentence_end + 1

            # Fallback to word boundary
            if end < len(text):
                search_start = max(start + self.chunk_size - 100, start)
                word_boundary = text.rfind(' ', search_start, end)
                if word_boundary > start + self.chunk_size * 0.8:
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

            start = end - self.chunk_overlap
            if start >= len(text):
                break

        return chunks

    def store_document_chunks(self, db: Session, document_id: str, chunks: List[Dict[str, Any]]):
        """Store document chunks in the database."""
        try:
            db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()

            for chunk in chunks:
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
        """Retrieve all chunks for a document."""
        return db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).order_by(DocumentChunk.chunk_index).all()

    def delete_document_chunks(self, db: Session, document_id: str):
        """Delete all chunks for a document."""
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
        """Compute embeddings for document chunks using OpenAI."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set; skipping embeddings")
            return 0

        client = OpenAI(api_key=api_key)
        chunks = self.get_document_chunks(db, document_id)
        if not chunks:
            return 0

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
        """Embed all chunks for documents in a paper."""
        from app.models.document import Document
        docs = db.query(Document).filter(Document.paper_id == paper_id).all()
        total = 0
        for d in docs:
            total += self.embed_document_chunks(db, str(d.id), model=model)
        return total

    def reprocess_document(self, db: Session, document: Document) -> bool:
        """
        Force reprocess a document (useful for re-extracting with new pipeline).
        """
        try:
            # Reset processing status
            document.is_processed_for_ai = False
            db.commit()

            # Delete existing chunks
            self.delete_document_chunks(db, str(document.id))

            # Reprocess
            return self.process_document_for_ai(db, document)

        except Exception as e:
            logger.error(f"Error reprocessing document {document.id}: {e}")
            db.rollback()
            return False
