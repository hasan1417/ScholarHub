"""empty message

Revision ID: 4a0d20610192
Revises: 82182748213f, d8f9b7a3c2f1
Create Date: 2025-11-03 11:29:04.068797

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4a0d20610192'
down_revision: Union[str, None] = ('82182748213f', 'd8f9b7a3c2f1')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
