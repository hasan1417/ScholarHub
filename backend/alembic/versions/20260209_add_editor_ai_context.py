"""Add editor_ai_context JSONB column to research_papers

Revision ID: 20260209_editor_ai_context
Revises: 20260206_annotations
Create Date: 2026-02-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic
revision = '20260209_editor_ai_context'
down_revision = '20260206_annotations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'research_papers',
        sa.Column('editor_ai_context', JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    # Add index for shared-scope history queries (paper_id only, no user_id)
    op.create_index(
        'ix_editor_chat_messages_paper_created_at',
        'editor_chat_messages',
        ['paper_id', 'created_at'],
    )


def downgrade() -> None:
    op.drop_index('ix_editor_chat_messages_paper_created_at', table_name='editor_chat_messages')
    op.drop_column('research_papers', 'editor_ai_context')
