"""add project sync sessions

Revision ID: c7b2e1d3a8f0
Revises: 8a42f6b93a36
Create Date: 2025-09-23 14:32:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c7b2e1d3a8f0'
down_revision: Union[str, None] = '8a42f6b93a36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYNC_SESSION_STATUS = postgresql.ENUM('scheduled', 'live', 'ended', 'cancelled', name='syncsessionstatus')
SYNC_MESSAGE_ROLE = postgresql.ENUM('participant', 'ai', 'system', name='syncmessagerole')


def upgrade() -> None:
    bind = op.get_bind()
    SYNC_SESSION_STATUS.create(bind, checkfirst=True)
    SYNC_MESSAGE_ROLE.create(bind, checkfirst=True)

    session_status_col = postgresql.ENUM('scheduled', 'live', 'ended', 'cancelled', name='syncsessionstatus', create_type=False)
    message_role_col = postgresql.ENUM('participant', 'ai', 'system', name='syncmessagerole', create_type=False)

    op.create_table(
        'project_sync_sessions',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('project_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('started_by', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('status', session_status_col, nullable=False, server_default='scheduled'),
        sa.Column('provider', sa.String(length=100), nullable=True),
        sa.Column('provider_room_id', sa.String(length=255), nullable=True),
        sa.Column('provider_payload', postgresql.JSONB(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['started_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'project_sync_messages',
        sa.Column('id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', sa.UUID(as_uuid=True), nullable=False),
        sa.Column('author_id', sa.UUID(as_uuid=True), nullable=True),
        sa.Column('role', message_role_col, nullable=False, server_default='participant'),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('is_command', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('command', sa.String(length=100), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['project_sync_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index('ix_project_sync_sessions_project', 'project_sync_sessions', ['project_id'])
    op.create_index('ix_project_sync_messages_session', 'project_sync_messages', ['session_id'])

    op.add_column('meetings', sa.Column('session_id', sa.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        'fk_meetings_session',
        'meetings',
        'project_sync_sessions',
        ['session_id'],
        ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_meetings_session', 'meetings', type_='foreignkey')
    op.drop_column('meetings', 'session_id')

    op.drop_index('ix_project_sync_messages_session', table_name='project_sync_messages')
    op.drop_table('project_sync_messages')

    op.drop_index('ix_project_sync_sessions_project', table_name='project_sync_sessions')
    op.drop_table('project_sync_sessions')

    bind = op.get_bind()
    SYNC_MESSAGE_ROLE.drop(bind, checkfirst=True)
    SYNC_SESSION_STATUS.drop(bind, checkfirst=True)
