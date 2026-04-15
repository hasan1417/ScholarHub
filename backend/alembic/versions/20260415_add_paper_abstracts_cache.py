"""add paper_abstracts cache table

Revision ID: 20260415_add_paper_abstracts_cache
Revises: 20260317_add_reference_entry_type
Create Date: 2026-04-15
"""
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260415_add_paper_abstracts_cache"
down_revision: Union[str, None] = "20260317_add_reference_entry_type"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.create_table(
        "paper_abstracts",
        sa.Column("doi", sa.String(255), primary_key=True),
        sa.Column("abstract", sa.Text(), nullable=True),
        sa.Column("source", sa.String(50), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="fresh"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "fetched_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_paper_abstracts_status_fetched",
        "paper_abstracts",
        ["status", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_paper_abstracts_status_fetched", table_name="paper_abstracts")
    op.drop_table("paper_abstracts")
