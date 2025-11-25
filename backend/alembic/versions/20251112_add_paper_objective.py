"""add objective column to research papers

Revision ID: add_paper_objective
Revises: 8d9e6f9ac4f1
Create Date: 2025-11-12 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
revision = 'add_paper_objective'
down_revision = '8d9e6f9ac4f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('research_papers', sa.Column('objective', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('research_papers', 'objective')
