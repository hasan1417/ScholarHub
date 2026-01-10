"""merge_channel_scope

Revision ID: d05be80ccbc2
Revises: 20260108_channel_scope, 8c204081ae93
Create Date: 2026-01-08 23:16:13.589335

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd05be80ccbc2'
down_revision: Union[str, None] = ('20260108_channel_scope', '8c204081ae93')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
