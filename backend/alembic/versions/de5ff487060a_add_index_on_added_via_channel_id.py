"""add_index_on_added_via_channel_id

Revision ID: de5ff487060a
Revises: 32fc05cd8192
Create Date: 2026-01-26 13:16:08.861947

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de5ff487060a'
down_revision: Union[str, None] = '32fc05cd8192'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        'ix_project_references_added_via_channel_id',
        'project_references',
        ['added_via_channel_id'],
        unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_project_references_added_via_channel_id', table_name='project_references')
