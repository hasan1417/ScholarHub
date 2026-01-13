"""Add conversation_state column to assistant exchanges

Revision ID: add_conversation_state
Revises:
Create Date: 2026-01-13

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = 'add_conversation_state'
down_revision = 'd05be80ccbc2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add conversation_state column with default empty JSON object
    op.add_column(
        'project_discussion_assistant_exchanges',
        sa.Column('conversation_state', JSONB, nullable=False, server_default='{}')
    )


def downgrade() -> None:
    op.drop_column('project_discussion_assistant_exchanges', 'conversation_state')
