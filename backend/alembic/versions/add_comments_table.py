"""create comments table

Revision ID: add_comments_table
Revises: add_compilation_fields_to_commits
Create Date: 2025-09-10 12:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'add_comments_table'
down_revision = 'add_compilation_fields_to_commits'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'comments',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('paper_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('research_papers.id'), nullable=False),
        sa.Column('commit_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('commits.id'), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('resolved', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now())
    )
    op.create_index('ix_comments_paper_id', 'comments', ['paper_id'])
    op.create_index('ix_comments_commit_id', 'comments', ['commit_id'])
    op.create_index('ix_comments_user_id', 'comments', ['user_id'])


def downgrade():
    op.drop_index('ix_comments_user_id', table_name='comments')
    op.drop_index('ix_comments_commit_id', table_name='comments')
    op.drop_index('ix_comments_paper_id', table_name='comments')
    op.drop_table('comments')

