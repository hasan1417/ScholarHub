"""add discussion embeddings table

Revision ID: 8d9e6f9ac4f1
Revises: 096deef3c80b
Create Date: 2025-10-03 14:45:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '8d9e6f9ac4f1'
down_revision = '096deef3c80b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'project_discussion_embeddings',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('origin_type', sa.Enum('RESOURCE', 'MESSAGE', 'TASK', 'ARTIFACT', name='discussion_embedding_origin'), nullable=False),
        sa.Column('origin_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('text_signature', sa.String(length=64), nullable=False),
        sa.Column('embedding', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('stale', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.ForeignKeyConstraint(['channel_id'], ['project_discussion_channels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('origin_type', 'origin_id', name='uq_discussion_embedding_origin'),
    )
    op.create_index(
        'ix_discussion_embeddings_channel',
        'project_discussion_embeddings',
        ['channel_id'],
    )
    op.create_index(
        'ix_discussion_embeddings_project',
        'project_discussion_embeddings',
        ['project_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_discussion_embeddings_project', table_name='project_discussion_embeddings')
    op.drop_index('ix_discussion_embeddings_channel', table_name='project_discussion_embeddings')
    op.drop_table('project_discussion_embeddings')
    sa.Enum(name='discussion_embedding_origin').drop(op.get_bind(), checkfirst=False)
