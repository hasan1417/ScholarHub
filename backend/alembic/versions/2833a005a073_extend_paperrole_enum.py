"""extend_paperrole_enum

Revision ID: 2833a005a073
Revises: f30835da2971
Create Date: 2025-09-20 11:50:49.155043

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2833a005a073'
down_revision: Union[str, None] = 'f30835da2971'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE paperrole ADD VALUE IF NOT EXISTS 'reviewer'")


def downgrade() -> None:
    # Removing enum values is not straightforward; leaving as no-op.
    pass
