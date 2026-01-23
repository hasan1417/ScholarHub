"""Fix document_chunks embedding column type from json to vector(1536)

Revision ID: fix_embedding_column_type
Revises: add_slug_short_id_001
Create Date: 2026-01-23 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'fix_embedding_column_type'
down_revision = 'add_slug_short_id_001'
branch_labels = None
depends_on = None


def upgrade():
    # Ensure pgvector extension is enabled
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Drop the existing json column and recreate as vector(1536)
    # We can't directly alter json to vector, so we need to drop and recreate
    op.drop_column('document_chunks', 'embedding')
    op.execute('ALTER TABLE document_chunks ADD COLUMN embedding vector(1536)')


def downgrade():
    # Convert back to json (will lose any vector data)
    op.drop_column('document_chunks', 'embedding')
    op.add_column('document_chunks', sa.Column('embedding', sa.JSON(), nullable=True))
