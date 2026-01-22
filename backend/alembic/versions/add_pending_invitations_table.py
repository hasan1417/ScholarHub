"""Add pending_invitations table for inviting unregistered users

Revision ID: add_pending_invitations
Revises:
Create Date: 2026-01-22

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_pending_invitations'
down_revision = 'add_subscription_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'pending_invitations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(50), nullable=False, server_default='viewer'),
        sa.Column('invited_by', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['invited_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_pending_invitations_email', 'pending_invitations', ['email'])
    op.create_index('ix_pending_invitations_email_project', 'pending_invitations', ['email', 'project_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_pending_invitations_email_project', table_name='pending_invitations')
    op.drop_index('ix_pending_invitations_email', table_name='pending_invitations')
    op.drop_table('pending_invitations')
