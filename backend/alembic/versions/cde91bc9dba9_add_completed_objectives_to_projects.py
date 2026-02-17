"""Add completed_objectives to projects

Revision ID: cde91bc9dba9
Revises: 20260212_zotero
Create Date: 2026-02-16 17:00:02.152723

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = "cde91bc9dba9"
down_revision: Union[str, None] = "20260212_zotero"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column(
            "completed_objectives",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("projects", "completed_objectives")
