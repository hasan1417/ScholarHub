"""Add ai_memory column to project_discussion_channels

Revision ID: add_ai_memory_001
Revises:
Create Date: 2026-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_ai_memory_001'
down_revision = 'add_pending_invitations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ai_memory JSONB column to project_discussion_channels
    op.add_column(
        'project_discussion_channels',
        sa.Column('ai_memory', postgresql.JSONB(astext_type=sa.Text()), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('project_discussion_channels', 'ai_memory')
