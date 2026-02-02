"""Add paper_embeddings and embedding_jobs tables for semantic search

Revision ID: 20260202_paper_embeddings
Revises: c7e91ecb3a2c
Create Date: 2026-02-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260202_paper_embeddings'
down_revision = 'c7e91ecb3a2c'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Ensure pgvector extension is enabled
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create paper_embeddings table
    op.create_table(
        'paper_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),

        # Reference - link to library paper OR external paper from search
        sa.Column('project_reference_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('external_paper_id', sa.String(length=255), nullable=True),

        # Content fingerprint for deduplication
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('embedded_text', sa.Text(), nullable=False),

        # Model info
        sa.Column('model_name', sa.String(length=100), nullable=False, server_default='all-MiniLM-L6-v2'),
        sa.Column('model_version', sa.String(length=50), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),

        # Constraints
        sa.ForeignKeyConstraint(
            ['project_reference_id'],
            ['project_references.id'],
            ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )

    # Add vector column (384 dimensions for all-MiniLM-L6-v2)
    op.execute('ALTER TABLE paper_embeddings ADD COLUMN embedding vector(384) NOT NULL')

    # Create HNSW index for fast approximate nearest neighbor search
    # Parameters: m=16 (connections per layer), ef_construction=64 (build-time search width)
    op.execute('''
        CREATE INDEX idx_paper_embeddings_hnsw
        ON paper_embeddings
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
    ''')

    # Create unique constraints
    op.create_index(
        'ix_paper_embeddings_reference_unique',
        'paper_embeddings',
        ['project_reference_id'],
        unique=True,
        postgresql_where=sa.text('project_reference_id IS NOT NULL')
    )
    op.create_index(
        'ix_paper_embeddings_external_model',
        'paper_embeddings',
        ['external_paper_id', 'model_name'],
        unique=True,
        postgresql_where=sa.text('external_paper_id IS NOT NULL')
    )

    # Lookup indexes
    op.create_index('ix_paper_embeddings_content_hash', 'paper_embeddings', ['content_hash'])

    # Create embedding_jobs table for async processing
    op.create_table(
        'embedding_jobs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),

        # Job type and target
        sa.Column('job_type', sa.String(length=50), nullable=False),  # 'library_paper', 'search_cache', 'bulk_reindex'
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=True),  # project_reference_id for library_paper
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=True),  # For bulk operations

        # Status tracking
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_attempts', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('error_message', sa.Text(), nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),

        # Constraints
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint("status IN ('pending', 'processing', 'completed', 'failed')", name='ck_embedding_jobs_status'),
    )

    # Index for job queue polling
    op.create_index(
        'ix_embedding_jobs_pending',
        'embedding_jobs',
        ['status', 'created_at'],
        postgresql_where=sa.text("status = 'pending'")
    )


def downgrade() -> None:
    # Drop embedding_jobs table
    op.drop_index('ix_embedding_jobs_pending', table_name='embedding_jobs')
    op.drop_table('embedding_jobs')

    # Drop paper_embeddings table
    op.drop_index('ix_paper_embeddings_content_hash', table_name='paper_embeddings')
    op.drop_index('ix_paper_embeddings_external_model', table_name='paper_embeddings')
    op.drop_index('ix_paper_embeddings_reference_unique', table_name='paper_embeddings')
    op.execute('DROP INDEX IF EXISTS idx_paper_embeddings_hnsw')
    op.drop_table('paper_embeddings')
