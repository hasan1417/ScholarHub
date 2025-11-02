"""add_branch_management_tables

Revision ID: branch_mgmt_001
Revises: cb17e54df25d
Create Date: 2025-08-30 11:52:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = 'branch_mgmt_001'
down_revision = 'cb17e54df25d'
branch_labels = None
depends_on = None


def upgrade():
    # Create branches table
    op.create_table('branches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('paper_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('research_papers.id'), nullable=False),
        sa.Column('parent_branch_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('branches.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('status', sa.String(50), default='active'),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('last_commit_message', sa.Text, default=''),
        sa.Column('is_main', sa.Boolean, default=False)
    )

    # Create commits table
    op.create_table('commits',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('branch_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('content', sa.Text, nullable=False),
        sa.Column('content_json', postgresql.JSON, nullable=True),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('changes', postgresql.JSON, nullable=False, default='[]')
    )

    # Create merge_requests table
    op.create_table('merge_requests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('source_branch_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('target_branch_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('branches.id'), nullable=False),
        sa.Column('paper_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('research_papers.id'), nullable=False),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('description', sa.Text),
        sa.Column('status', sa.String(50), default='open'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('author_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('conflicts', postgresql.JSON, nullable=True)
    )

    # Create conflict_resolutions table
    op.create_table('conflict_resolutions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('merge_request_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('merge_requests.id'), nullable=False),
        sa.Column('section', sa.String(255), nullable=False),
        sa.Column('source_content', sa.Text),
        sa.Column('target_content', sa.Text),
        sa.Column('resolved_content', sa.Text),
        sa.Column('status', sa.String(50), default='unresolved'),
        sa.Column('resolution_strategy', sa.String(50), default='manual'),
        sa.Column('resolved_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id'), nullable=True),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True)
    )

    # Create indexes
    op.create_index('ix_branches_paper_id', 'branches', ['paper_id'])
    op.create_index('ix_branches_author_id', 'branches', ['author_id'])
    op.create_index('ix_commits_branch_id', 'commits', ['branch_id'])
    op.create_index('ix_commits_author_id', 'commits', ['author_id'])
    op.create_index('ix_commits_timestamp', 'commits', ['timestamp'])
    op.create_index('ix_merge_requests_paper_id', 'merge_requests', ['paper_id'])
    op.create_index('ix_merge_requests_author_id', 'merge_requests', ['author_id'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_merge_requests_author_id', 'merge_requests')
    op.drop_index('ix_merge_requests_paper_id', 'merge_requests')
    op.drop_index('ix_commits_timestamp', 'commits')
    op.drop_index('ix_commits_author_id', 'commits')
    op.drop_index('ix_commits_branch_id', 'commits')
    op.drop_index('ix_branches_author_id', 'branches')
    op.drop_index('ix_branches_paper_id', 'branches')
    
    # Drop tables
    op.drop_table('conflict_resolutions')
    op.drop_table('merge_requests')
    op.drop_table('commits')
    op.drop_table('branches')
