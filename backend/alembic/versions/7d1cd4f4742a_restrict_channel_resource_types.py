"""restrict channel resources to papers, references, and meetings

Revision ID: 7d1cd4f4742a
Revises: 096deef3c80b
Create Date: 2025-10-06 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7d1cd4f4742a"
down_revision: Union[str, None] = "096deef3c80b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_CHECK = "(" \
    "(resource_type = 'paper' AND paper_id IS NOT NULL AND reference_id IS NULL AND meeting_id IS NULL AND tag IS NULL AND external_url IS NULL)" \
    " OR " \
    "(resource_type = 'reference' AND reference_id IS NOT NULL AND paper_id IS NULL AND meeting_id IS NULL AND tag IS NULL AND external_url IS NULL)" \
    " OR " \
    "(resource_type = 'meeting' AND meeting_id IS NOT NULL AND paper_id IS NULL AND reference_id IS NULL AND tag IS NULL AND external_url IS NULL)" \
    ")"

_OLD_CHECK = "(" \
    "(resource_type = 'paper' AND paper_id IS NOT NULL AND reference_id IS NULL AND meeting_id IS NULL AND tag IS NULL AND external_url IS NULL)" \
    " OR " \
    "(resource_type = 'reference' AND reference_id IS NOT NULL AND paper_id IS NULL AND meeting_id IS NULL AND tag IS NULL AND external_url IS NULL)" \
    " OR " \
    "(resource_type = 'meeting' AND meeting_id IS NOT NULL AND paper_id IS NULL AND reference_id IS NULL AND tag IS NULL AND external_url IS NULL)" \
    " OR " \
    "(resource_type = 'tag' AND tag IS NOT NULL AND paper_id IS NULL AND reference_id IS NULL AND meeting_id IS NULL AND external_url IS NULL)" \
    " OR " \
    "(resource_type = 'external' AND external_url IS NOT NULL AND paper_id IS NULL AND reference_id IS NULL AND meeting_id IS NULL AND tag IS NULL)" \
    ")"


def upgrade() -> None:
    op.execute(
        "DELETE FROM project_discussion_channel_resources "
        "WHERE resource_type IN ('tag', 'external')"
    )
    op.drop_constraint(
        "ck_discussion_channel_resource_target",
        "project_discussion_channel_resources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_discussion_channel_resource_target",
        "project_discussion_channel_resources",
        _NEW_CHECK,
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_discussion_channel_resource_target",
        "project_discussion_channel_resources",
        type_="check",
    )
    op.create_check_constraint(
        "ck_discussion_channel_resource_target",
        "project_discussion_channel_resources",
        _OLD_CHECK,
    )
