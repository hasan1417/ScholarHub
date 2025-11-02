"""add_project_discussion_messages

Revision ID: 1ac5270db9ab
Revises: 2dbc9d249eb0
Create Date: 2025-10-02 09:02:11.402872

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '1ac5270db9ab'
down_revision: Union[str, None] = '2dbc9d249eb0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'project_discussion_messages',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('project_id', UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('parent_id', UUID(as_uuid=True), sa.ForeignKey('project_discussion_messages.id', ondelete='CASCADE'), nullable=True),
        sa.Column('is_edited', sa.Boolean(), default=False),
        sa.Column('is_deleted', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Create indexes for better query performance
    op.create_index('ix_project_discussion_messages_project_id', 'project_discussion_messages', ['project_id'])
    op.create_index('ix_project_discussion_messages_user_id', 'project_discussion_messages', ['user_id'])
    op.create_index('ix_project_discussion_messages_parent_id', 'project_discussion_messages', ['parent_id'])
    op.create_index('ix_project_discussion_messages_created_at', 'project_discussion_messages', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_project_discussion_messages_created_at', table_name='project_discussion_messages')
    op.drop_index('ix_project_discussion_messages_parent_id', table_name='project_discussion_messages')
    op.drop_index('ix_project_discussion_messages_user_id', table_name='project_discussion_messages')
    op.drop_index('ix_project_discussion_messages_project_id', table_name='project_discussion_messages')
    op.drop_table('project_discussion_messages')
