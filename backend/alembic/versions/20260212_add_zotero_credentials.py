"""add zotero credentials to users

Revision ID: 20260212_zotero
Revises: 20260210_credit_system
Create Date: 2026-02-12

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260212_zotero"
down_revision: Union[str, None] = "20260210_credit_system"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("zotero_api_key", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("zotero_user_id", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "zotero_user_id")
    op.drop_column("users", "zotero_api_key")
