"""add_byok_tier

Revision ID: add_byok_tier_001
Revises: 4138c3e33bbc
Create Date: 2026-01-29

Adds the BYOK (Bring Your Own Key) tier for users who provide their own API keys.
This tier has unlimited AI features since users are paying for their own API usage.
Also adds previous_tier_id column to track original tier when switching to BYOK.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'add_byok_tier_001'
down_revision: Union[str, None] = '4138c3e33bbc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add previous_tier_id column to track original tier before BYOK
    op.add_column(
        'user_subscriptions',
        sa.Column('previous_tier_id', sa.String(50), nullable=True)
    )

    # Add BYOK tier - unlimited AI features since user pays for their own API
    op.execute("""
        INSERT INTO subscription_tiers (id, name, price_monthly_cents, limits, is_active) VALUES
        ('byok', 'BYOK (Bring Your Own Key)', 0, '{
            "discussion_ai_calls": -1,
            "paper_discovery_searches": -1,
            "projects": 10,
            "papers_per_project": 50,
            "collaborators_per_project": 5,
            "references_total": 200
        }', true)
        ON CONFLICT (id) DO UPDATE SET
            limits = EXCLUDED.limits,
            is_active = true
    """)


def downgrade() -> None:
    # Remove BYOK tier
    op.execute("DELETE FROM subscription_tiers WHERE id = 'byok'")

    # Remove previous_tier_id column
    op.drop_column('user_subscriptions', 'previous_tier_id')
