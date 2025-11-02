"""add table for discussion assistant history

Revision ID: 9f85b0d5b1a2
Revises: 7d1cd4f4742a
Create Date: 2025-10-06 17:29:00.000000

"""

from __future__ import annotations

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9f85b0d5b1a2"
down_revision: Union[str, None] = "7d1cd4f4742a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_discussion_assistant_exchanges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("response", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_index(
        "ix_discussion_assistant_channel_created",
        "project_discussion_assistant_exchanges",
        ["channel_id", "created_at"],
    )

    op.create_index(
        "ix_discussion_assistant_author",
        "project_discussion_assistant_exchanges",
        ["author_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_discussion_assistant_author", table_name="project_discussion_assistant_exchanges")
    op.drop_index("ix_discussion_assistant_channel_created", table_name="project_discussion_assistant_exchanges")
    op.drop_table("project_discussion_assistant_exchanges")
