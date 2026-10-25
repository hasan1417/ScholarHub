"""add library proxy prefix to users

Revision ID: 20261025_library_proxy_prefix
Revises: 20260831_fk_query_indexes
Create Date: 2026-10-25

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20261025_library_proxy_prefix"
down_revision: Union[str, None] = "20260831_fk_query_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("library_proxy_prefix", sa.String(500), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "library_proxy_prefix")
