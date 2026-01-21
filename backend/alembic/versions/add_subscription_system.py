"""add_subscription_system

Revision ID: add_subscription_001
Revises: add_oauth_fields_001
Create Date: 2026-01-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'add_subscription_001'
down_revision: Union[str, None] = 'add_oauth_fields_001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create subscription_tiers reference table
    op.create_table(
        'subscription_tiers',
        sa.Column('id', sa.String(50), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('price_monthly_cents', sa.Integer, nullable=False, server_default='0'),
        sa.Column('limits', postgresql.JSONB, nullable=False, server_default='{}'),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
    )

    # Create user_subscriptions table
    op.create_table(
        'user_subscriptions',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('tier_id', sa.String(50), nullable=False, server_default='free'),
        sa.Column('status', sa.String(20), nullable=False, server_default='active'),
        sa.Column('current_period_start', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('stripe_customer_id', sa.String(255), nullable=True),
        sa.Column('stripe_subscription_id', sa.String(255), nullable=True),
        sa.Column('custom_limits', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['tier_id'], ['subscription_tiers.id']),
        sa.UniqueConstraint('user_id', name='uq_user_subscription'),
    )
    op.create_index('ix_user_subscriptions_user_id', 'user_subscriptions', ['user_id'])

    # Create usage_tracking table
    op.create_table(
        'usage_tracking',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('period_year', sa.Integer, nullable=False),
        sa.Column('period_month', sa.Integer, nullable=False),
        sa.Column('discussion_ai_calls', sa.Integer, nullable=False, server_default='0'),
        sa.Column('paper_discovery_searches', sa.Integer, nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'period_year', 'period_month', name='uq_usage_user_period'),
    )
    op.create_index('ix_usage_tracking_user_id', 'usage_tracking', ['user_id'])

    # Seed default tiers
    op.execute("""
        INSERT INTO subscription_tiers (id, name, price_monthly_cents, limits, is_active) VALUES
        ('free', 'Free', 0, '{
            "discussion_ai_calls": 20,
            "paper_discovery_searches": 10,
            "projects": 3,
            "papers_per_project": 10,
            "collaborators_per_project": 2,
            "references_total": 50
        }', true),
        ('pro', 'Pro', 1500, '{
            "discussion_ai_calls": 500,
            "paper_discovery_searches": 200,
            "projects": 25,
            "papers_per_project": 100,
            "collaborators_per_project": 10,
            "references_total": 500
        }', true)
    """)


def downgrade() -> None:
    op.drop_index('ix_usage_tracking_user_id', table_name='usage_tracking')
    op.drop_table('usage_tracking')
    op.drop_index('ix_user_subscriptions_user_id', table_name='user_subscriptions')
    op.drop_table('user_subscriptions')
    op.drop_table('subscription_tiers')
