"""add commit state field

Revision ID: add_commit_state
Revises: drop_latex_crdt_snapshots
Create Date: 2025-09-10 12:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_commit_state'
down_revision = 'drop_latex_crdt_snapshots'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('commits', sa.Column('state', sa.String(length=32), nullable=False, server_default='draft'))


def downgrade():
    op.drop_column('commits', 'state')

