"""add document_snapshots table for history feature

Revision ID: 20260103_snapshots
Revises: 20251113_paper_objectives_array
Create Date: 2026-01-03

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260103_snapshots"
down_revision: Union[str, None] = "20251113_paper_objectives_array"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "document_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_papers.id", ondelete="CASCADE"), nullable=False),

        # Yjs state
        sa.Column("yjs_state", sa.LargeBinary(), nullable=False),
        sa.Column("materialized_text", sa.Text(), nullable=True),

        # Snapshot metadata
        sa.Column("snapshot_type", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("label", sa.String(255), nullable=True),

        # Authorship
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),

        # Sequence tracking for timeline
        sa.Column("sequence_number", sa.Integer(), nullable=False),

        # Size tracking
        sa.Column("text_length", sa.Integer(), nullable=True),
    )

    # Create indexes
    op.create_index(
        "ix_document_snapshots_paper_created",
        "document_snapshots",
        ["paper_id", "created_at"],
    )
    op.create_index(
        "ix_document_snapshots_paper_sequence",
        "document_snapshots",
        ["paper_id", "sequence_number"],
    )
    op.create_index(
        "ix_document_snapshots_type",
        "document_snapshots",
        ["snapshot_type"],
    )

    # Unique constraint for paper + sequence
    op.create_unique_constraint(
        "uq_document_snapshots_paper_sequence",
        "document_snapshots",
        ["paper_id", "sequence_number"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_document_snapshots_paper_sequence", "document_snapshots", type_="unique")
    op.drop_index("ix_document_snapshots_type", table_name="document_snapshots")
    op.drop_index("ix_document_snapshots_paper_sequence", table_name="document_snapshots")
    op.drop_index("ix_document_snapshots_paper_created", table_name="document_snapshots")
    op.drop_table("document_snapshots")
