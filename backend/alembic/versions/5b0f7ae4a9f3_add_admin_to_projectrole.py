"""add_admin_to_projectrole

Revision ID: 5b0f7ae4a9f3
Revises: 7b9923bb594d
Create Date: 2025-09-21 18:45:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "5b0f7ae4a9f3"
down_revision: Union[str, None] = "7b9923bb594d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE projectrole ADD VALUE IF NOT EXISTS 'admin'")


def downgrade() -> None:
    # Enum value removal is non-trivial and could orphan existing rows; leave as no-op.
    pass
