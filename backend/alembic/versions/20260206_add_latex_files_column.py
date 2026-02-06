"""Add latex_files JSONB column to research_papers

Revision ID: 20260206_latex_files
Revises: 20260203_editor_chat_messages
Create Date: 2026-02-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic
revision = '20260206_latex_files'
down_revision = '20260203_editor_chat_messages'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('research_papers', sa.Column('latex_files', JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column('research_papers', 'latex_files')
