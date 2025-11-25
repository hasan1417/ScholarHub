"""placeholder migration for missing revision 8c204081ae93

Revision ID: 8c204081ae93
Revises: 8d9e6f9ac4f1
Create Date: 2025-11-12 00:30:00.000000

This migration was missing from the repository but recorded in the database.
It performs no schema changes; it simply keeps Alembic's history consistent.
"""

from alembic import op
import sqlalchemy as sa
from typing import Sequence, Union

revision = '8c204081ae93'
down_revision = '8d9e6f9ac4f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
