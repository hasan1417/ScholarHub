"""Add editor_chat_messages table for LaTeX editor AI memory

Revision ID: 20260203_editor_chat_messages
Revises: 20260202_paper_embeddings
Create Date: 2026-02-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '20260203_editor_chat_messages'
down_revision = '20260202_paper_embeddings'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'editor_chat_messages',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('paper_id', sa.String(length=128), nullable=True),
        sa.Column('project_id', sa.String(length=128), nullable=True),
        sa.Column('role', sa.String(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_editor_chat_messages_user_paper_created_at',
        'editor_chat_messages',
        ['user_id', 'paper_id', 'created_at'],
    )
    op.create_index(
        'ix_editor_chat_messages_user_project_created_at',
        'editor_chat_messages',
        ['user_id', 'project_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_editor_chat_messages_user_project_created_at', table_name='editor_chat_messages')
    op.drop_index('ix_editor_chat_messages_user_paper_created_at', table_name='editor_chat_messages')
    op.drop_table('editor_chat_messages')
