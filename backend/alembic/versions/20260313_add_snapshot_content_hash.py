"""add content hash to document snapshots

Revision ID: 20260313_snapshot_content_hash
Revises: 20260302_paper_chat
Create Date: 2026-03-13
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260313_snapshot_content_hash"
down_revision: Union[str, None] = "20260302_paper_chat"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "document_snapshots",
        sa.Column("content_hash", sa.String(length=16), nullable=True),
    )
    op.create_index(
        "ix_document_snapshots_content_hash",
        "document_snapshots",
        ["content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_document_snapshots_content_hash", table_name="document_snapshots")
    op.drop_column("document_snapshots", "content_hash")
