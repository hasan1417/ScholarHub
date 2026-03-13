"""Add is_paper_chat flag to discussion channels

Revision ID: 20260302_paper_chat
Revises: 20260301_extraction_quality
Create Date: 2026-03-02
"""
from typing import Union

from alembic import op
import sqlalchemy as sa

revision: str = "20260302_paper_chat"
down_revision: Union[str, None] = "20260301_extraction_quality"
branch_labels: Union[str, None] = None
depends_on: Union[str, None] = None


def upgrade() -> None:
    op.add_column(
        "project_discussion_channels",
        sa.Column("is_paper_chat", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("project_discussion_channels", "is_paper_chat")
