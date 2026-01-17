"""add_discussion_artifacts_table

Revision ID: f1a4dd9dbd60
Revises: add_conversation_state
Create Date: 2026-01-14 08:01:48.076850

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f1a4dd9dbd60'
down_revision: Union[str, None] = 'add_conversation_state'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create the discussion_artifacts table (enum is created automatically)
    op.create_table('discussion_artifacts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('channel_id', sa.UUID(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('filename', sa.String(length=500), nullable=False),
        sa.Column('format', sa.Enum('markdown', 'pdf', 'latex', 'text', name='discussionartifactformat', create_type=True), nullable=False),
        sa.Column('artifact_type', sa.String(length=100), nullable=False),
        sa.Column('content_base64', sa.Text(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=False),
        sa.Column('file_size', sa.String(length=50), nullable=True),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['channel_id'], ['project_discussion_channels.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )

    # Add index for faster channel lookups
    op.create_index('ix_discussion_artifacts_channel_id', 'discussion_artifacts', ['channel_id'])


def downgrade() -> None:
    op.drop_index('ix_discussion_artifacts_channel_id', table_name='discussion_artifacts')
    op.drop_table('discussion_artifacts')

    # Drop the enum type
    sa.Enum(name='discussionartifactformat').drop(op.get_bind(), checkfirst=True)
