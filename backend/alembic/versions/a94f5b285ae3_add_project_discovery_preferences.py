"""add_project_discovery_preferences

Revision ID: a94f5b285ae3
Revises: 8a42f6b93a36
Create Date: 2025-09-20 15:20:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a94f5b285ae3'
down_revision: Union[str, None] = '8a42f6b93a36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column(
            'discovery_preferences',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column('projects', 'discovery_preferences')
