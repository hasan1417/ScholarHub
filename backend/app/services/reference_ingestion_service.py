"""Utilities for ingesting reference PDFs into the document pipeline."""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional
from urllib.parse import urljoin

import requests
from requests import Response
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus, DocumentType
from app.models.document_chunk import DocumentChunk
from app.models.reference import Reference
from app.models.research_paper import ResearchPaper
from app.services.document_service import DocumentService

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Execute an async coroutine from synchronous context.

    Uses a thread pool to properly handle running async code when
    an event loop is already running (e.g., from FastAPI).
    """
    import concurrent.futures

    def run_in_thread():
        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Run in a separate thread to avoid nested event loop issues
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(run_in_thread)
            return future.result(timeout=60)

    return asyncio.run(coro)


def _sanitize_filename(title: Optional[str]) -> str:
    base = title or "reference"
    base = base.strip().lower()[:96]
    base = re.sub(r"[^a-z0-9_-]+", "-", base)
    base = base.strip("-") or "reference"
    return f"{base}.pdf"


def _resolve_owner_id(db: Session, reference: Reference, fallback_owner: Optional[str] = None) -> str:
    if reference.paper_id:
        paper = db.query(ResearchPaper).filter(ResearchPaper.id == reference.paper_id).first()
        if paper and paper.owner_id:
            return str(paper.owner_id)
    if reference.owner_id:
        return str(reference.owner_id)
    if fallback_owner:
        return str(fallback_owner)
    raise ValueError("Unable to resolve owner for reference document ingestion")


def _fetch_pdf(url: str) -> Optional[Response]:
    # Use browser-like headers to avoid bot blocking by publishers
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/pdf,*/*",
    }
    try:
        resp = requests.get(url, timeout=30, headers=headers, allow_redirects=True)
    except Exception as exc:  # pragma: no cover - network variability
        logger.warning("Failed to download PDF from %s: %s", url, exc)
        return None

    if resp.status_code != 200:
        logger.info("PDF download from %s returned status %s", url, resp.status_code)
        return None

    content_type = (resp.headers.get("content-type") or "").lower()
    # Accept PDF content-type, octet-stream (common for downloads), or URLs ending in .pdf
    is_pdf_content = "pdf" in content_type or "octet-stream" in content_type
    is_pdf_url = url.lower().endswith(".pdf") or "download" in url.lower()
    if not is_pdf_content and not is_pdf_url:
        logger.info("Downloaded content from %s is not a PDF (content-type=%s)", url, content_type)
        return None

    if not resp.content:
        logger.info("Downloaded PDF from %s is empty", url)
        return None

    return resp


def ingest_reference_pdf(
    db: Session,
    reference: Reference,
    *,
    owner_id: Optional[str] = None,
) -> bool:
    """Download a reference PDF, store it as a document, and chunk it for AI."""

    if not getattr(reference, "pdf_url", None):
        return False

    existing_document: Optional[Document] = None
    if getattr(reference, "document_id", None):
        existing_document = db.query(Document).filter(Document.id == reference.document_id).first()

    # If document already exists and is processed, ensure status reflects it
    if existing_document and existing_document.status == DocumentStatus.PROCESSED and existing_document.is_processed_for_ai:
        if reference.status != 'analyzed':
            reference.status = 'analyzed'
            try:
                db.commit()
            except Exception:
                db.rollback()
        return True

    ds = DocumentService()

    # Download PDF when no document is stored yet
    if not existing_document:
        base_url = reference.url or ""
        pdf_url = urljoin(base_url, reference.pdf_url)
        response = _fetch_pdf(pdf_url)
        if response is None:
            return False

        filename = _sanitize_filename(reference.title)

        try:
            file_path = _run_async(ds.save_uploaded_file(response.content, filename))
        except Exception as exc:
            logger.error("Unable to persist downloaded PDF for reference %s: %s", reference.id, exc)
            return False

        try:
            resolved_owner = _resolve_owner_id(db, reference, owner_id)
        except ValueError as exc:
            logger.warning("Skipping PDF ingestion for reference %s: %s", reference.id, exc)
            return False

        document = Document(
            filename=filename,
            original_filename=filename,
            file_path=file_path,
            file_size=len(response.content),
            mime_type="application/pdf",
            document_type=DocumentType.PDF,
            file_hash=ds.duplicate_detector.calculate_file_hash(response.content),
            title=reference.title,
            doi=reference.doi,
            journal=reference.journal,
            owner_id=resolved_owner,
            paper_id=reference.paper_id,
            status=DocumentStatus.PROCESSING,
        )

        # Use savepoint to avoid affecting outer transaction on failure
        try:
            with db.begin_nested():
                db.add(document)
            db.commit()
            db.refresh(document)
        except Exception as exc:
            db.rollback()
            logger.error("Failed to create document record for reference %s: %s", reference.id, exc)
            return False

        document_bytes = response.content
    else:
        document = existing_document
        try:
            with open(document.file_path, 'rb') as fh:
                document_bytes = fh.read()
        except Exception as exc:
            logger.error("Failed to read stored PDF for reference %s: %s", reference.id, exc)
            return False

    # Re-run document processing
    try:
        _run_async(ds.process_document(db, document, document_bytes, None))
    except Exception as exc:  # pragma: no cover - best effort
        logger.warning("Document processing for reference %s failed: %s", reference.id, exc)

    # Link chunks to reference - use expire_all instead of rollback to preserve outer transaction
    try:
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).all()
        for chunk in chunks:
            chunk.reference_id = reference.id
        if chunks:
            db.commit()
    except Exception as exc:  # pragma: no cover - chunk linking best effort
        db.expire_all()  # Clear stale state without affecting committed data
        logger.warning("Failed linking chunks to reference %s: %s", reference.id, exc)

    # Update reference status
    reference.document_id = document.id
    reference.status = 'analyzed'
    try:
        db.commit()
    except Exception as exc:
        db.expire_all()  # Clear stale state without affecting committed data
        logger.warning("Failed to persist reference %s after PDF ingestion: %s", reference.id, exc)
        return False

    logger.info("Ingested or refreshed PDF for reference %s", reference.id)
    return True
