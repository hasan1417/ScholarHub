"""add_discussion_settings_to_projects

Revision ID: 9f7386efdf23
Revises: add_byok_tier_001
Create Date: 2026-01-29 18:00:23.991075

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = '9f7386efdf23'
down_revision: Union[str, None] = 'add_byok_tier_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add discussion_settings JSONB column to projects
    op.add_column(
        'projects',
        sa.Column(
            'discussion_settings',
            JSONB,
            nullable=False,
            server_default='{"enabled": true, "model": "openai/gpt-5.2-20251211"}'
        )
    )


def downgrade() -> None:
    op.drop_column('projects', 'discussion_settings')
