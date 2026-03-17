"""add entry_type to references

Revision ID: 20260317_add_reference_entry_type
Revises: 20260314_add_snapshot_files
Create Date: 2026-03-17
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260317_add_reference_entry_type"
down_revision: Union[str, None] = "20260314_add_snapshot_files"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column("references", sa.Column("entry_type", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("references", "entry_type")
