"""
Background worker for embedding generation.

Handles:
- Embedding library papers when added
- Bulk reindexing of project papers
- Cache maintenance

Usage:
    # Start worker in background thread (from FastAPI startup)
    from app.services.embedding_worker import start_embedding_worker, stop_embedding_worker

    @app.on_event("startup")
    async def startup():
        start_embedding_worker()

    @app.on_event("shutdown")
    async def shutdown():
        stop_embedding_worker()

    # Queue a job when paper is added to library
    queue_library_paper_embedding_sync(reference_id, project_id, db_session)
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update, text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.paper_embedding import EmbeddingJob, PaperEmbedding
from app.models.project_reference import ProjectReference
from app.models.reference import Reference
from app.services.embedding_service import (
    get_embedding_service_for_persistence,
    EmbeddingService,
    PERSISTED_EMBEDDING_DIMENSIONS,
)

logger = logging.getLogger(__name__)

# Global worker instance
_worker_instance: Optional["EmbeddingWorker"] = None
_worker_thread: Optional[threading.Thread] = None


class EmbeddingWorker:
    """
    Background worker that processes embedding jobs.

    Runs in a separate thread, polling the embedding_jobs table.
    Uses synchronous SQLAlchemy sessions (matches rest of app).
    """

    BATCH_SIZE = 10
    POLL_INTERVAL = 5  # seconds
    MAX_RETRIES = 3

    def __init__(self, embedding_service: Optional[EmbeddingService] = None):
        """
        Initialize the worker.

        Args:
            embedding_service: Optional embedding service (uses default if not provided)
        """
        self.embedding_service = embedding_service or get_embedding_service_for_persistence()
        self._running = False

    def start(self):
        """Start the background worker loop (blocking - run in thread)."""
        if self._running:
            logger.warning("[EmbeddingWorker] Already running")
            return

        self._running = True
        logger.info("[EmbeddingWorker] Starting background worker")

        while self._running:
            try:
                processed = self._process_pending_jobs()
                if processed > 0:
                    logger.debug(f"[EmbeddingWorker] Processed {processed} jobs")
            except Exception as e:
                logger.error(f"[EmbeddingWorker] Error in worker loop: {e}")

            time.sleep(self.POLL_INTERVAL)

        logger.info("[EmbeddingWorker] Worker stopped")

    def stop(self):
        """Stop the background worker."""
        logger.info("[EmbeddingWorker] Stopping worker")
        self._running = False

    def _process_pending_jobs(self) -> int:
        """Process pending embedding jobs. Returns number of jobs processed."""
        db = SessionLocal()
        try:
            jobs = self._claim_pending_jobs(db)
            if not jobs:
                return 0

            processed = 0
            for job in jobs:
                success = self._process_job(db, job, already_processing=True)
                if success:
                    processed += 1

            return processed
        finally:
            db.close()

    def _claim_pending_jobs(self, db: Session) -> list[EmbeddingJob]:
        """Atomically claim pending jobs and mark them as processing."""
        now = datetime.now(timezone.utc)
        stmt = text("""
            UPDATE embedding_jobs
            SET status = 'processing',
                started_at = :now,
                attempts = attempts + 1
            WHERE id IN (
                SELECT id FROM embedding_jobs
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT :limit
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id
        """)
        rows = db.execute(stmt, {"now": now, "limit": self.BATCH_SIZE}).fetchall()
        db.commit()

        if not rows:
            return []

        job_ids = [row[0] for row in rows]
        return db.query(EmbeddingJob).filter(EmbeddingJob.id.in_(job_ids)).all()

    def _process_job(self, db: Session, job: EmbeddingJob, *, already_processing: bool = False) -> bool:
        """Process a single embedding job. Returns True if completed successfully."""
        logger.debug(f"[EmbeddingWorker] Processing job {job.id} (type={job.job_type})")

        # Mark as processing and increment attempts unless already claimed
        if not already_processing:
            self._mark_job_processing(db, job)

        try:
            if job.job_type == "library_paper":
                self._embed_library_paper(db, job.target_id)
            elif job.job_type == "bulk_reindex":
                self._bulk_reindex_project(db, job.project_id)
            else:
                raise ValueError(f"Unknown job type: {job.job_type}")

            self._mark_job_completed(db, job)
            return True

        except Exception as e:
            # Check attempts (already incremented when claimed/processing)
            max_attempts = job.max_attempts or self.MAX_RETRIES
            if job.attempts < max_attempts:
                # Retry later - mark as pending, don't raise
                logger.warning(f"[EmbeddingWorker] Job {job.id} failed (attempt {job.attempts}/{max_attempts}): {e}")
                self._mark_job_pending(db, job)
                return False
            else:
                # Max retries exceeded - mark as failed
                logger.error(f"[EmbeddingWorker] Job {job.id} failed permanently after {job.attempts} attempts: {e}")
                self._mark_job_failed(db, job, str(e))
                return False

    def _embed_library_paper(self, db: Session, reference_id: UUID):
        """Embed a single library paper."""
        if not reference_id:
            raise ValueError("No reference_id provided")

        # Fetch the reference with its paper data
        stmt = (
            select(ProjectReference, Reference)
            .join(Reference, ProjectReference.reference_id == Reference.id)
            .where(ProjectReference.id == reference_id)
        )
        row = db.execute(stmt).first()

        if not row:
            logger.warning(f"[EmbeddingWorker] Reference {reference_id} not found")
            return

        project_ref, reference = row

        # Check if embedding already exists
        existing = db.query(PaperEmbedding).filter(
            PaperEmbedding.project_reference_id == reference_id
        ).first()

        # Prepare text for embedding
        title = reference.title or ""
        abstract = reference.abstract or ""
        text = self.embedding_service.prepare_paper_text(title, abstract)
        content_hash = self.embedding_service.content_hash(text)

        # Skip if content unchanged
        if existing and existing.content_hash == content_hash:
            logger.debug(f"[EmbeddingWorker] Embedding unchanged for {reference_id}")
            return

        # Generate embedding (run async in sync context)
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            embedding = loop.run_until_complete(self.embedding_service.embed(text))
        finally:
            loop.close()

        if existing:
            # Update existing
            existing.embedding = embedding
            existing.embedded_text = text
            existing.content_hash = content_hash
            existing.model_name = self.embedding_service.model_name
            existing.updated_at = datetime.now(timezone.utc)
        else:
            # Create new
            paper_embedding = PaperEmbedding(
                project_reference_id=reference_id,
                content_hash=content_hash,
                embedded_text=text,
                embedding=embedding,
                model_name=self.embedding_service.model_name,
            )
            db.add(paper_embedding)

        db.commit()
        logger.info(f"[EmbeddingWorker] Embedded paper for reference {reference_id}")

    def _bulk_reindex_project(self, db: Session, project_id: UUID):
        """Re-embed all papers in a project."""
        if not project_id:
            raise ValueError("No project_id provided")

        # Fetch all references in the project
        stmt = (
            select(ProjectReference, Reference)
            .join(Reference, ProjectReference.reference_id == Reference.id)
            .where(ProjectReference.project_id == project_id)
        )
        rows = db.execute(stmt).all()

        logger.info(f"[EmbeddingWorker] Bulk reindexing {len(rows)} papers for project {project_id}")

        for project_ref, _ in rows:
            try:
                self._embed_library_paper(db, project_ref.id)
            except Exception as e:
                logger.error(f"[EmbeddingWorker] Failed to embed {project_ref.id}: {e}")
                # Continue with other papers

        logger.info(f"[EmbeddingWorker] Completed bulk reindex for project {project_id}")

    def _mark_job_processing(self, db: Session, job: EmbeddingJob):
        """Mark job as processing and increment attempts."""
        new_attempts = job.attempts + 1
        stmt = (
            update(EmbeddingJob)
            .where(EmbeddingJob.id == job.id)
            .values(
                status="processing",
                started_at=datetime.now(timezone.utc),
                attempts=new_attempts
            )
        )
        db.execute(stmt)
        db.commit()
        # Update in-memory object so retry logic sees correct attempt count
        job.attempts = new_attempts

    def _mark_job_completed(self, db: Session, job: EmbeddingJob):
        """Mark job as completed."""
        stmt = (
            update(EmbeddingJob)
            .where(EmbeddingJob.id == job.id)
            .values(
                status="completed",
                completed_at=datetime.now(timezone.utc)
            )
        )
        db.execute(stmt)
        db.commit()

    def _mark_job_failed(self, db: Session, job: EmbeddingJob, error: str):
        """Mark job as failed."""
        stmt = (
            update(EmbeddingJob)
            .where(EmbeddingJob.id == job.id)
            .values(
                status="failed",
                error_message=error[:1000],  # Truncate long errors
                completed_at=datetime.now(timezone.utc)
            )
        )
        db.execute(stmt)
        db.commit()

    def _mark_job_pending(self, db: Session, job: EmbeddingJob):
        """Mark job as pending for retry."""
        stmt = (
            update(EmbeddingJob)
            .where(EmbeddingJob.id == job.id)
            .values(status="pending")
        )
        db.execute(stmt)
        db.commit()


# === Global worker management ===

def start_embedding_worker():
    """Start the embedding worker in a background thread."""
    global _worker_instance, _worker_thread

    if _worker_thread is not None and _worker_thread.is_alive():
        logger.warning("[EmbeddingWorker] Worker already running")
        return

    _worker_instance = EmbeddingWorker()
    _worker_thread = threading.Thread(target=_worker_instance.start, daemon=True)
    _worker_thread.start()
    logger.info("[EmbeddingWorker] Background thread started")


def stop_embedding_worker():
    """Stop the embedding worker."""
    global _worker_instance, _worker_thread

    if _worker_instance is not None:
        _worker_instance.stop()

    if _worker_thread is not None:
        _worker_thread.join(timeout=10)
        _worker_thread = None

    _worker_instance = None
    logger.info("[EmbeddingWorker] Background thread stopped")


# === Helper functions for queueing jobs ===

def queue_library_paper_embedding_sync(
    reference_id: UUID,
    project_id: UUID,
    db: Session
) -> EmbeddingJob:
    """
    Queue an embedding job for a library paper.

    Call this when a paper is added to a project library.
    """
    job = EmbeddingJob(
        job_type="library_paper",
        target_id=reference_id,
        project_id=project_id,
        status="pending"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.debug(f"[EmbeddingWorker] Queued embedding job for reference {reference_id}")
    return job


def queue_bulk_reindex_sync(
    project_id: UUID,
    db: Session
) -> EmbeddingJob:
    """
    Queue a bulk reindex job for all papers in a project.

    Call this when switching embedding models or fixing issues.
    """
    job = EmbeddingJob(
        job_type="bulk_reindex",
        project_id=project_id,
        status="pending"
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    logger.info(f"[EmbeddingWorker] Queued bulk reindex for project {project_id}")
    return job
