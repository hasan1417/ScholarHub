"""add realtime latex state columns

Revision ID: d8f9b7a3c2f1
Revises: 4b2f2cb03b75
Create Date: 2025-10-14 12:26:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d8f9b7a3c2f1"
down_revision: Union[str, None] = "4b2f2cb03b75"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("research_papers", sa.Column("latex_crdt_state", sa.LargeBinary(), nullable=True))
    op.add_column(
        "research_papers",
        sa.Column("latex_crdt_rev", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column("research_papers", sa.Column("latex_crdt_checksum", sa.String(length=64), nullable=True))
    op.add_column(
        "research_papers",
        sa.Column("latex_crdt_synced_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_index(
        "ix_research_papers_latex_crdt_synced_at",
        "research_papers",
        ["latex_crdt_synced_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_research_papers_latex_crdt_synced_at", table_name="research_papers")
    op.drop_column("research_papers", "latex_crdt_synced_at")
    op.drop_column("research_papers", "latex_crdt_checksum")
    op.drop_column("research_papers", "latex_crdt_rev")
    op.drop_column("research_papers", "latex_crdt_state")

