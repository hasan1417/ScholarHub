"""Add refresh token reuse fields

Revision ID: 8c204081ae93
Revises: 4a0d20610192
Create Date: 2025-11-03 11:29:26.014550

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c204081ae93'
down_revision: Union[str, None] = '4a0d20610192'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', sa.Column('refresh_token_last_hash', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('refresh_token_last_seen_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'refresh_token_last_seen_at')
    op.drop_column('users', 'refresh_token_last_hash')
