"""Add added_via_channel_id to project_references

Revision ID: 32fc05cd8192
Revises: cb59a8efb643
Create Date: 2026-01-26 12:54:26.747884

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '32fc05cd8192'
down_revision: Union[str, None] = 'cb59a8efb643'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add column to track which channel added this reference
    op.add_column('project_references', sa.Column('added_via_channel_id', sa.UUID(), nullable=True))
    op.create_foreign_key(
        'fk_project_references_channel',
        'project_references',
        'project_discussion_channels',
        ['added_via_channel_id'],
        ['id'],
        ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_project_references_channel', 'project_references', type_='foreignkey')
    op.drop_column('project_references', 'added_via_channel_id')
