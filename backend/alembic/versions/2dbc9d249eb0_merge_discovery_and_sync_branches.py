"""merge discovery and sync branches

Revision ID: 2dbc9d249eb0
Revises: 5b0f7ae4a9f3, c7b2e1d3a8f0
Create Date: 2025-09-25 14:39:26.736485

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2dbc9d249eb0'
down_revision: Union[str, None] = ('5b0f7ae4a9f3', 'c7b2e1d3a8f0')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
