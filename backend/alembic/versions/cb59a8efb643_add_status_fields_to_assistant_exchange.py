"""Add status fields to assistant exchange

Revision ID: cb59a8efb643
Revises: fix_embedding_column_type
Create Date: 2026-01-24 14:46:13.790515

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'cb59a8efb643'
down_revision: Union[str, None] = 'fix_embedding_column_type'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add status fields to track background processing
    op.add_column('project_discussion_assistant_exchanges',
                  sa.Column('status', sa.String(length=20), server_default='completed', nullable=False))
    op.add_column('project_discussion_assistant_exchanges',
                  sa.Column('status_message', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('project_discussion_assistant_exchanges', 'status_message')
    op.drop_column('project_discussion_assistant_exchanges', 'status')
