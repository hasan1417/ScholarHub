"""Add extraction_quality to documents

Revision ID: 20260301_extraction_quality
Revises: 20260217_byok_limits
Create Date: 2026-03-01

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260301_extraction_quality"
down_revision: Union[str, None] = "20260217_byok_limits"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("extraction_quality", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("documents", "extraction_quality")
