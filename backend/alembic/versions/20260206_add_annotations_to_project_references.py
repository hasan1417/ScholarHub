"""Add annotations JSONB column to project_references

Revision ID: 20260206_annotations
Revises: 20260206_latex_files
Create Date: 2026-02-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic
revision = '20260206_annotations'
down_revision = '20260206_latex_files'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'project_references',
        sa.Column('annotations', JSONB, nullable=True, server_default='{}'),
    )


def downgrade() -> None:
    op.drop_column('project_references', 'annotations')
