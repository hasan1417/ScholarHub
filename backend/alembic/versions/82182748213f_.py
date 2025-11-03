"""empty message

Revision ID: 82182748213f
Revises: 8d9e6f9ac4f1, 9f85b0d5b1a2
Create Date: 2025-11-03 11:28:41.434823

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82182748213f'
down_revision: Union[str, None] = ('8d9e6f9ac4f1', '9f85b0d5b1a2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
