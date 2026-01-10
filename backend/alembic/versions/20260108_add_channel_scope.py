"""add scope field to discussion channels

Revision ID: 20260108_channel_scope
Revises: 20260103_snapshots
Create Date: 2026-01-08

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260108_channel_scope"
down_revision: Union[str, None] = "20260103_snapshots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add scope column to project_discussion_channels
    # null = project-wide (all resources)
    # array of strings = specific scope, e.g. ["papers", "references", "transcripts"]
    op.add_column(
        "project_discussion_channels",
        sa.Column("scope", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("project_discussion_channels", "scope")
