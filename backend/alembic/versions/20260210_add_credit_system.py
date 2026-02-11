"""add_credit_system

Revision ID: 20260210_credit_system
Revises: 20260209_editor_ai_context
Create Date: 2026-02-10

Switches AI billing from per-call to credit-based:
- Adds editor_ai_calls column (separate counter from discussion)
- Adds tokens_consumed column (internal cost tracking, not user-facing)
- Updates tier limits to credit-based values
- Bumps paper_discovery_searches for free tier (free API, no cost)
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '20260210_credit_system'
down_revision: Union[str, None] = '20260209_editor_ai_context'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns to usage_tracking
    op.add_column(
        'usage_tracking',
        sa.Column('editor_ai_calls', sa.Integer, nullable=False, server_default='0')
    )
    op.add_column(
        'usage_tracking',
        sa.Column('tokens_consumed', sa.BigInteger, nullable=False, server_default='0')
    )

    # Update tier limits to credit-based values
    # Free: 50 credits discussion, 50 editor, 30 discovery (was 20/20/10)
    op.execute("""
        UPDATE subscription_tiers
        SET limits = '{
            "discussion_ai_calls": 50,
            "editor_ai_calls": 50,
            "paper_discovery_searches": 30,
            "projects": 3,
            "papers_per_project": 10,
            "collaborators_per_project": 2,
            "references_total": 50
        }'
        WHERE id = 'free'
    """)

    # Pro: 1000 credits each, 200 discovery
    op.execute("""
        UPDATE subscription_tiers
        SET limits = '{
            "discussion_ai_calls": 1000,
            "editor_ai_calls": 1000,
            "paper_discovery_searches": 200,
            "projects": 25,
            "papers_per_project": 100,
            "collaborators_per_project": 10,
            "references_total": 500
        }'
        WHERE id = 'pro'
    """)

    # BYOK: unlimited AI, keep resource limits
    op.execute("""
        UPDATE subscription_tiers
        SET limits = '{
            "discussion_ai_calls": -1,
            "editor_ai_calls": -1,
            "paper_discovery_searches": -1,
            "projects": 10,
            "papers_per_project": 50,
            "collaborators_per_project": 5,
            "references_total": 200
        }'
        WHERE id = 'byok'
    """)


def downgrade() -> None:
    # Revert tier limits
    op.execute("""
        UPDATE subscription_tiers
        SET limits = '{
            "discussion_ai_calls": 20,
            "paper_discovery_searches": 10,
            "projects": 3,
            "papers_per_project": 10,
            "collaborators_per_project": 2,
            "references_total": 50
        }'
        WHERE id = 'free'
    """)
    op.execute("""
        UPDATE subscription_tiers
        SET limits = '{
            "discussion_ai_calls": 500,
            "paper_discovery_searches": 200,
            "projects": 25,
            "papers_per_project": 100,
            "collaborators_per_project": 10,
            "references_total": 500
        }'
        WHERE id = 'pro'
    """)
    op.execute("""
        UPDATE subscription_tiers
        SET limits = '{
            "discussion_ai_calls": -1,
            "paper_discovery_searches": -1,
            "projects": 10,
            "papers_per_project": 50,
            "collaborators_per_project": 5,
            "references_total": 200
        }'
        WHERE id = 'byok'
    """)

    op.drop_column('usage_tracking', 'tokens_consumed')
    op.drop_column('usage_tracking', 'editor_ai_calls')
