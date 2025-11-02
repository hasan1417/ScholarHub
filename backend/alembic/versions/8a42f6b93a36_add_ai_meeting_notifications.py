"""add_ai_meeting_notifications

Revision ID: 8a42f6b93a36
Revises: 2833a005a073
Create Date: 2025-09-20 11:51:05.769298

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '8a42f6b93a36'
down_revision: Union[str, None] = '2833a005a073'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ai_artifact_type = postgresql.ENUM('summary', 'litReview', 'outline', 'directoryHelp', 'intent', name='aiartifacttype')
    ai_artifact_status = postgresql.ENUM('queued', 'running', 'succeeded', 'failed', name='aiartifactstatus')
    meeting_status = postgresql.ENUM('uploaded', 'transcribing', 'completed', 'failed', name='meetingstatus')

    ai_artifact_type.create(op.get_bind(), checkfirst=True)
    ai_artifact_status.create(op.get_bind(), checkfirst=True)
    meeting_status.create(op.get_bind(), checkfirst=True)

    ai_artifact_type_col = postgresql.ENUM('summary', 'litReview', 'outline', 'directoryHelp', 'intent', name='aiartifacttype', create_type=False)
    ai_artifact_status_col = postgresql.ENUM('queued', 'running', 'succeeded', 'failed', name='aiartifactstatus', create_type=False)
    meeting_status_col = postgresql.ENUM('uploaded', 'transcribing', 'completed', 'failed', name='meetingstatus', create_type=False)

    op.create_table(
        'ai_artifacts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('paper_id', sa.UUID(), nullable=True),
        sa.Column('type', ai_artifact_type_col, nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('status', ai_artifact_status_col, nullable=False, server_default='queued'),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.CheckConstraint('project_id IS NOT NULL OR paper_id IS NOT NULL', name='ck_ai_artifact_has_target'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['paper_id'], ['research_papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'meetings',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('created_by', sa.UUID(), nullable=True),
        sa.Column('status', meeting_status_col, nullable=False, server_default='uploaded'),
        sa.Column('audio_url', sa.String(length=1000), nullable=True),
        sa.Column('transcript', postgresql.JSONB(), nullable=True),
        sa.Column('summary', sa.String(), nullable=True),
        sa.Column('action_items', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_table(
        'notifications',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=True),
        sa.Column('type', sa.String(length=100), nullable=False),
        sa.Column('payload', postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column('read', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    op.create_index('ix_ai_artifacts_project', 'ai_artifacts', ['project_id'])
    op.create_index('ix_ai_artifacts_paper', 'ai_artifacts', ['paper_id'])
    op.create_index('ix_meetings_project', 'meetings', ['project_id'])
    op.create_index('ix_notifications_user', 'notifications', ['user_id'])
    op.create_index('ix_notifications_project', 'notifications', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_notifications_project', table_name='notifications')
    op.drop_index('ix_notifications_user', table_name='notifications')
    op.drop_table('notifications')

    op.drop_index('ix_meetings_project', table_name='meetings')
    op.drop_table('meetings')

    op.drop_index('ix_ai_artifacts_paper', table_name='ai_artifacts')
    op.drop_index('ix_ai_artifacts_project', table_name='ai_artifacts')
    op.drop_table('ai_artifacts')

    op.execute('DROP TYPE IF EXISTS meetingstatus')
    op.execute('DROP TYPE IF EXISTS aiartifactstatus')
    op.execute('DROP TYPE IF EXISTS aiartifacttype')
