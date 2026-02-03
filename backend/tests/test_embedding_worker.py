"""
Tests for embedding worker and semantic search flow.

Tests the full pipeline:
1. Paper added to library → embedding job queued
2. Worker processes job → embedding generated
3. Embedding stored in pgvector
4. Semantic search returns relevant papers
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.paper_embedding import EmbeddingJob, PaperEmbedding
from app.models.project_reference import ProjectReference
from app.models.reference import Reference
from app.services.embedding_worker import (
    EmbeddingWorker,
    queue_library_paper_embedding_sync,
    queue_bulk_reindex_sync,
)


# --- Fixtures ---

@pytest.fixture
def test_reference(db: Session, test_project, test_user):
    """Create a test reference with paper data."""
    ref = Reference(
        id=uuid.uuid4(),
        title="Deep Learning for Natural Language Processing: A Survey",
        abstract="This paper provides a comprehensive survey of deep learning methods applied to natural language processing tasks including sentiment analysis, machine translation, and question answering.",
        doi="10.1234/test.doi.12345",
        source="test",
        owner_id=test_user.id,
    )
    db.add(ref)
    db.flush()

    project_ref = ProjectReference(
        id=uuid.uuid4(),
        project_id=test_project.id,
        reference_id=ref.id,
        status="approved",
    )
    db.add(project_ref)
    db.commit()
    db.refresh(project_ref)

    yield project_ref, ref

    # Cleanup
    try:
        db.query(PaperEmbedding).filter(
            PaperEmbedding.project_reference_id == project_ref.id
        ).delete()
        db.query(EmbeddingJob).filter(
            EmbeddingJob.target_id == project_ref.id
        ).delete()
        db.delete(project_ref)
        db.delete(ref)
        db.commit()
    except Exception:
        db.rollback()


@pytest.fixture
def mock_embedding_service():
    """Mock embedding service that returns deterministic 384-dim vectors."""
    service = MagicMock()
    service.model_name = "all-MiniLM-L6-v2"
    service.dimensions = 384

    def mock_prepare_paper_text(title, abstract=None, max_abstract_len=2000):
        parts = [f"Title: {title}"]
        if abstract:
            parts.append(f"Abstract: {abstract[:max_abstract_len]}")
        return "\n".join(parts)

    service.prepare_paper_text = mock_prepare_paper_text

    def mock_content_hash(text):
        import hashlib
        return hashlib.sha256(text.strip().lower().encode()).hexdigest()

    service.content_hash = mock_content_hash

    # Return a deterministic 384-dim embedding
    async def mock_embed(text):
        # Generate deterministic embedding based on text hash
        import hashlib
        h = hashlib.md5(text.encode()).hexdigest()
        seed = int(h[:8], 16)
        import random
        random.seed(seed)
        return [random.uniform(-1, 1) for _ in range(384)]

    service.embed = AsyncMock(side_effect=mock_embed)

    return service


# --- Test: Job Queueing ---

class TestJobQueueing:
    """Tests for embedding job queue creation."""

    def test_queue_library_paper_creates_job(self, db: Session, test_reference, test_project):
        """Adding paper to library queues an embedding job."""
        project_ref, _ = test_reference

        job = queue_library_paper_embedding_sync(
            reference_id=project_ref.id,
            project_id=test_project.id,
            db=db,
        )

        assert job is not None
        assert job.job_type == "library_paper"
        assert job.target_id == project_ref.id
        assert job.project_id == test_project.id
        assert job.status == "pending"
        assert job.attempts == 0

    def test_queue_bulk_reindex_creates_job(self, db: Session, test_project):
        """Bulk reindex queues a job for all project papers."""
        job = queue_bulk_reindex_sync(
            project_id=test_project.id,
            db=db,
        )

        assert job is not None
        assert job.job_type == "bulk_reindex"
        assert job.project_id == test_project.id
        assert job.status == "pending"

    def test_multiple_jobs_queued_independently(self, db: Session, test_reference, test_project):
        """Multiple papers queue separate jobs."""
        project_ref, _ = test_reference

        job1 = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)
        job2 = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)

        assert job1.id != job2.id
        assert job1.status == "pending"
        assert job2.status == "pending"


# --- Test: Worker Processing ---

class TestWorkerProcessing:
    """Tests for embedding worker job processing."""

    def test_worker_claims_pending_jobs(self, db: Session, test_reference, test_project):
        """Worker claims pending jobs atomically."""
        project_ref, _ = test_reference

        # Queue a job
        queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)

        # Create worker and claim jobs
        worker = EmbeddingWorker()
        jobs = worker._claim_pending_jobs(db)

        assert len(jobs) >= 1
        # Job should now be processing
        claimed_job = db.query(EmbeddingJob).filter(
            EmbeddingJob.target_id == project_ref.id
        ).first()
        assert claimed_job.status == "processing"
        assert claimed_job.attempts == 1

    def test_worker_processes_library_paper_job(
        self, db: Session, test_reference, test_project, mock_embedding_service
    ):
        """Worker processes library paper job and creates embedding."""
        project_ref, ref = test_reference

        # Queue job
        job = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)

        # Create worker with mock service
        worker = EmbeddingWorker(embedding_service=mock_embedding_service)

        # Process the job
        success = worker._process_job(db, job, already_processing=False)

        assert success is True

        # Check embedding was created
        embedding = db.query(PaperEmbedding).filter(
            PaperEmbedding.project_reference_id == project_ref.id
        ).first()

        assert embedding is not None
        assert embedding.model_name == "all-MiniLM-L6-v2"
        assert "Deep Learning" in embedding.embedded_text
        assert embedding.content_hash is not None

    def test_worker_marks_job_completed(
        self, db: Session, test_reference, test_project, mock_embedding_service
    ):
        """Worker marks job as completed after successful processing."""
        project_ref, _ = test_reference

        job = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)

        worker = EmbeddingWorker(embedding_service=mock_embedding_service)
        worker._process_job(db, job, already_processing=False)

        # Refresh job from DB
        db.refresh(job)
        assert job.status == "completed"
        assert job.completed_at is not None

    def test_worker_retries_on_failure(self, db: Session, test_reference, test_project):
        """Worker retries failed jobs up to max_attempts."""
        project_ref, _ = test_reference

        job = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)

        # Create worker with failing service
        failing_service = MagicMock()
        failing_service.prepare_paper_text = MagicMock(side_effect=Exception("API error"))

        worker = EmbeddingWorker(embedding_service=failing_service)
        success = worker._process_job(db, job, already_processing=False)

        assert success is False
        db.refresh(job)
        # Should be pending for retry, not failed (first attempt)
        assert job.status == "pending"
        assert job.attempts == 1

    def test_worker_marks_failed_after_max_retries(
        self, db: Session, test_reference, test_project
    ):
        """Worker marks job as failed after max retries exceeded."""
        project_ref, _ = test_reference

        job = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)
        # Simulate previous attempts
        job.attempts = 3  # Already at max
        db.commit()

        failing_service = MagicMock()
        failing_service.prepare_paper_text = MagicMock(side_effect=Exception("API error"))

        worker = EmbeddingWorker(embedding_service=failing_service)
        worker.MAX_RETRIES = 3
        success = worker._process_job(db, job, already_processing=False)

        assert success is False
        db.refresh(job)
        assert job.status == "failed"
        assert "API error" in job.error_message

    def test_worker_respects_job_max_attempts(
        self, db: Session, test_reference, test_project
    ):
        """Worker uses job.max_attempts when set."""
        project_ref, _ = test_reference

        job = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)
        job.max_attempts = 1  # Override default
        job.attempts = 1
        db.commit()

        failing_service = MagicMock()
        failing_service.prepare_paper_text = MagicMock(side_effect=Exception("error"))

        worker = EmbeddingWorker(embedding_service=failing_service)
        worker._process_job(db, job, already_processing=False)

        db.refresh(job)
        # Should fail immediately since max_attempts=1 and attempts=1
        assert job.status == "failed"


# --- Test: Embedding Storage ---

class TestEmbeddingStorage:
    """Tests for embedding storage in pgvector."""

    def test_embedding_has_correct_dimensions(
        self, db: Session, test_reference, test_project, mock_embedding_service
    ):
        """Stored embedding has 384 dimensions."""
        project_ref, _ = test_reference

        job = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)

        worker = EmbeddingWorker(embedding_service=mock_embedding_service)
        worker._process_job(db, job, already_processing=False)

        # Check dimensions using pgvector function
        result = db.execute(
            text("""
                SELECT vector_dims(embedding)
                FROM paper_embeddings
                WHERE project_reference_id = :ref_id
            """),
            {"ref_id": str(project_ref.id)}
        ).fetchone()

        assert result is not None
        assert result[0] == 384

    def test_embedding_updates_on_content_change(
        self, db: Session, test_reference, test_project, mock_embedding_service
    ):
        """Embedding is updated when paper content changes."""
        project_ref, ref = test_reference

        # First embedding
        job1 = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)
        worker = EmbeddingWorker(embedding_service=mock_embedding_service)
        worker._process_job(db, job1, already_processing=False)

        embedding1 = db.query(PaperEmbedding).filter(
            PaperEmbedding.project_reference_id == project_ref.id
        ).first()
        original_hash = embedding1.content_hash

        # Update paper content
        ref.abstract = "Completely new abstract about quantum computing."
        db.commit()

        # Second embedding job
        job2 = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)
        worker._process_job(db, job2, already_processing=False)

        db.refresh(embedding1)
        # Hash should change with new content
        assert embedding1.content_hash != original_hash

    def test_embedding_skipped_if_content_unchanged(
        self, db: Session, test_reference, test_project, mock_embedding_service
    ):
        """Embedding generation is skipped if content hash matches."""
        project_ref, _ = test_reference

        # First embedding
        job1 = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)
        worker = EmbeddingWorker(embedding_service=mock_embedding_service)
        worker._process_job(db, job1, already_processing=False)

        call_count_before = mock_embedding_service.embed.call_count

        # Second job with same content
        job2 = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)
        worker._process_job(db, job2, already_processing=False)

        # embed() should not be called again
        assert mock_embedding_service.embed.call_count == call_count_before


# --- Test: Semantic Search ---

class TestSemanticSearch:
    """Tests for pgvector semantic similarity search."""

    def test_semantic_search_finds_relevant_paper(
        self, db: Session, test_reference, test_project, mock_embedding_service
    ):
        """Semantic search returns papers by similarity."""
        project_ref, _ = test_reference

        # Create embedding for paper
        job = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)
        worker = EmbeddingWorker(embedding_service=mock_embedding_service)
        worker._process_job(db, job, already_processing=False)

        # Search with similar query - generate embedding synchronously for test
        query = "neural networks and NLP deep learning"
        # Use the same deterministic embedding logic as mock
        import hashlib
        import random
        h = hashlib.md5(query.encode()).hexdigest()
        seed = int(h[:8], 16)
        random.seed(seed)
        query_embedding = [random.uniform(-1, 1) for _ in range(384)]

        # pgvector cosine similarity search
        result = db.execute(
            text("""
                SELECT pe.project_reference_id,
                       1 - (pe.embedding <=> cast(:query_vec as vector)) as similarity
                FROM paper_embeddings pe
                JOIN project_references pr ON pe.project_reference_id = pr.id
                WHERE pr.project_id = :project_id
                ORDER BY pe.embedding <=> cast(:query_vec as vector)
                LIMIT 5
            """),
            {
                "query_vec": str(query_embedding),
                "project_id": str(test_project.id)
            }
        ).fetchall()

        assert len(result) >= 1
        # Should find our paper
        found_ids = [str(r[0]) for r in result]
        assert str(project_ref.id) in found_ids
        # Similarity should be reasonable (> 0 for related content)
        similarity = result[0][1]
        assert similarity > 0

    def test_semantic_search_returns_multiple_papers_ranked(
        self, db: Session, test_project, test_user, mock_embedding_service
    ):
        """Semantic search returns multiple papers with similarity scores."""
        # Create two papers
        ref1 = Reference(
            id=uuid.uuid4(),
            title="Machine Learning for Computer Vision",
            abstract="Deep neural networks for image classification and object detection.",
            source="test",
            owner_id=test_user.id,
        )
        ref2 = Reference(
            id=uuid.uuid4(),
            title="History of Ancient Rome",
            abstract="The rise and fall of the Roman Empire from 753 BC to 476 AD.",
            source="test",
            owner_id=test_user.id,
        )
        db.add_all([ref1, ref2])
        db.flush()

        pr1 = ProjectReference(
            id=uuid.uuid4(),
            project_id=test_project.id,
            reference_id=ref1.id,
            status="approved",
        )
        pr2 = ProjectReference(
            id=uuid.uuid4(),
            project_id=test_project.id,
            reference_id=ref2.id,
            status="approved",
        )
        db.add_all([pr1, pr2])
        db.commit()

        # Generate embeddings for both
        worker = EmbeddingWorker(embedding_service=mock_embedding_service)
        for pr in [pr1, pr2]:
            job = queue_library_paper_embedding_sync(pr.id, test_project.id, db)
            worker._process_job(db, job, already_processing=False)

        # Search with any query - verify ranking mechanism works
        query = "test query for ranking"
        import hashlib
        import random
        h = hashlib.md5(query.encode()).hexdigest()
        seed = int(h[:8], 16)
        random.seed(seed)
        query_embedding = [random.uniform(-1, 1) for _ in range(384)]

        result = db.execute(
            text("""
                SELECT pe.project_reference_id,
                       1 - (pe.embedding <=> cast(:query_vec as vector)) as similarity
                FROM paper_embeddings pe
                JOIN project_references pr ON pe.project_reference_id = pr.id
                WHERE pr.project_id = :project_id
                ORDER BY pe.embedding <=> cast(:query_vec as vector)
                LIMIT 5
            """),
            {
                "query_vec": str(query_embedding),
                "project_id": str(test_project.id)
            }
        ).fetchall()

        # Should return both papers
        assert len(result) == 2
        # Both should have similarity scores
        for row in result:
            assert row[1] is not None  # similarity score exists
            assert -1 <= row[1] <= 1  # cosine similarity range
        # Results should be ordered (first has higher similarity)
        assert result[0][1] >= result[1][1]

        # Cleanup
        try:
            db.query(PaperEmbedding).filter(
                PaperEmbedding.project_reference_id.in_([pr1.id, pr2.id])
            ).delete(synchronize_session=False)
            db.query(EmbeddingJob).filter(
                EmbeddingJob.target_id.in_([pr1.id, pr2.id])
            ).delete(synchronize_session=False)
            db.delete(pr1)
            db.delete(pr2)
            db.delete(ref1)
            db.delete(ref2)
            db.commit()
        except Exception:
            db.rollback()


# --- Test: Thread Safety ---

class TestThreadSafety:
    """Tests for thread-safe operation."""

    def test_worker_uses_threading_lock(self):
        """Embedding service uses threading.Lock, not asyncio.Lock."""
        from app.services.embedding_service import SentenceTransformerProvider
        import threading

        provider = SentenceTransformerProvider()
        assert isinstance(provider._lock, type(threading.Lock()))

    def test_atomic_job_claiming_prevents_duplicates(self, db: Session, test_reference, test_project):
        """Atomic claiming prevents same job from being processed twice."""
        project_ref, _ = test_reference

        # Queue single job
        job = queue_library_paper_embedding_sync(project_ref.id, test_project.id, db)
        job_id = job.id

        # Simulate two workers claiming simultaneously
        worker1 = EmbeddingWorker()
        worker2 = EmbeddingWorker()

        # First claim succeeds
        jobs1 = worker1._claim_pending_jobs(db)

        # Second claim should get empty (job already claimed)
        jobs2 = worker2._claim_pending_jobs(db)

        # Only one worker should get the job
        claimed_job_ids = [j.id for j in jobs1] + [j.id for j in jobs2]
        assert claimed_job_ids.count(job_id) == 1
