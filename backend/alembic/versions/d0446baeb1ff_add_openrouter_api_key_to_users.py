"""Add openrouter_api_key to users

Revision ID: d0446baeb1ff
Revises: de5ff487060a
Create Date: 2026-01-27 21:24:32.336488

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd0446baeb1ff'
down_revision: Union[str, None] = 'de5ff487060a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('openrouter_api_key', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'openrouter_api_key')
