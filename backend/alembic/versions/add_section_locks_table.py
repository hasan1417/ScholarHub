"""create section_locks table

Revision ID: add_section_locks_table
Revises: add_commit_state
Create Date: 2025-09-10 12:55:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_section_locks_table'
down_revision = 'add_commit_state'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'section_locks',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('paper_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('research_papers.id'), nullable=False),
        sa.Column('section_key', sa.Text(), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index('ix_section_locks_paper_section', 'section_locks', ['paper_id', 'section_key'])


def downgrade():
    op.drop_index('ix_section_locks_paper_section', table_name='section_locks')
    op.drop_table('section_locks')

