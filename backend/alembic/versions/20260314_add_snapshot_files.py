"""add materialized_files to document snapshots

Revision ID: 20260314_add_snapshot_files
Revises: 20260313_snapshot_content_hash
Create Date: 2026-03-14
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260314_add_snapshot_files"
down_revision: Union[str, None] = "20260313_snapshot_content_hash"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("document_snapshots", sa.Column("materialized_files", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("document_snapshots", "materialized_files")
