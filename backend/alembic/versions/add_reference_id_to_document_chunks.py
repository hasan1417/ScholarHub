"""Add reference_id to document_chunks

Revision ID: add_reference_id_to_document_chunks
Revises: refs_owner_and_nullable_paper
Create Date: 2025-01-09 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_reference_id_to_document_chunks'
down_revision = 'refs_owner_and_nullable_paper'
branch_labels = None
depends_on = None


def upgrade():
    # Add reference_id column to document_chunks table
    op.add_column('document_chunks', sa.Column('reference_id', postgresql.UUID(as_uuid=True), nullable=True))
    
    # Add foreign key constraint
    op.create_foreign_key(
        'fk_document_chunks_reference_id',
        'document_chunks',
        'references',
        ['reference_id'],
        ['id'],
        ondelete='CASCADE'
    )


def downgrade():
    # Drop foreign key constraint
    op.drop_constraint('fk_document_chunks_reference_id', 'document_chunks', type_='foreignkey')
    
    # Drop reference_id column
    op.drop_column('document_chunks', 'reference_id')