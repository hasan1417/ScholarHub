"""add_project_discovery_runs_and_results

Revision ID: 3c8b4e0d3b21
Revises: a94f5b285ae3
Create Date: 2025-06-04 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3c8b4e0d3b21'
down_revision: Union[str, None] = 'a94f5b285ae3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    run_type_enum = sa.Enum('manual', 'auto', name='projectdiscoveryruntype')
    run_status_enum = sa.Enum(
        'pending',
        'running',
        'completed',
        'failed',
        name='projectdiscoveryrunstatus',
    )
    result_status_enum = sa.Enum(
        'pending',
        'promoted',
        'dismissed',
        name='projectdiscoveryresultstatus',
    )
    reference_origin_enum = sa.Enum(
        'unknown',
        'manual_discovery',
        'auto_discovery',
        'manual_add',
        'import',
        'upload',
        name='projectreferenceorigin',
    )

    run_type_enum.create(bind, checkfirst=True)
    run_status_enum.create(bind, checkfirst=True)
    result_status_enum.create(bind, checkfirst=True)
    reference_origin_enum.create(bind, checkfirst=True)

    op.create_table(
        'project_discovery_runs',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('run_type', run_type_enum, nullable=False),
        sa.Column('status', run_status_enum, nullable=False, server_default='pending'),
        sa.Column('triggered_by', sa.UUID(), nullable=True),
        sa.Column('query', sa.Text(), nullable=True),
        sa.Column('keywords', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('sources', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('max_results', sa.Integer(), nullable=True),
        sa.Column('relevance_threshold', sa.Float(), nullable=True),
        sa.Column('settings_snapshot', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['triggered_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_index(
        'ix_project_discovery_runs_project',
        'project_discovery_runs',
        ['project_id'],
    )
    op.create_index(
        'ix_project_discovery_runs_status',
        'project_discovery_runs',
        ['status'],
    )

    op.create_table(
        'project_discovery_results',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('run_id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('reference_id', sa.UUID(), nullable=True),
        sa.Column('status', result_status_enum, nullable=False, server_default='pending'),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('doi', sa.String(length=255), nullable=True),
        sa.Column('title', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('authors', postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column('published_year', sa.Integer(), nullable=True),
        sa.Column('relevance_score', sa.Float(), nullable=True),
        sa.Column('fingerprint', sa.String(length=128), nullable=False),
        sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('promoted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('dismissed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reference_id'], ['references.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['run_id'], ['project_discovery_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'project_id',
            'fingerprint',
            name='uq_project_discovery_result_fingerprint',
        ),
    )

    op.create_index(
        'ix_project_discovery_results_project',
        'project_discovery_results',
        ['project_id'],
    )
    op.create_index(
        'ix_project_discovery_results_status',
        'project_discovery_results',
        ['status'],
    )
    op.create_index(
        'ix_project_discovery_results_reference',
        'project_discovery_results',
        ['reference_id'],
    )

    op.add_column(
        'project_references',
        sa.Column('origin', reference_origin_enum, nullable=False, server_default='unknown'),
    )
    op.add_column(
        'project_references',
        sa.Column('discovery_run_id', sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        'fk_project_reference_discovery_run',
        'project_references',
        'project_discovery_runs',
        ['discovery_run_id'],
        ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_project_references_discovery_run',
        'project_references',
        ['discovery_run_id'],
    )
    op.execute("UPDATE project_references SET origin = 'unknown' WHERE origin IS NULL")


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index('ix_project_references_discovery_run', table_name='project_references')
    op.drop_constraint('fk_project_reference_discovery_run', 'project_references', type_='foreignkey')
    op.drop_column('project_references', 'discovery_run_id')
    op.drop_column('project_references', 'origin')

    op.drop_index('ix_project_discovery_results_reference', table_name='project_discovery_results')
    op.drop_index('ix_project_discovery_results_status', table_name='project_discovery_results')
    op.drop_index('ix_project_discovery_results_project', table_name='project_discovery_results')
    op.drop_table('project_discovery_results')

    op.drop_index('ix_project_discovery_runs_status', table_name='project_discovery_runs')
    op.drop_index('ix_project_discovery_runs_project', table_name='project_discovery_runs')
    op.drop_table('project_discovery_runs')

    sa.Enum(name='projectreferenceorigin').drop(bind, checkfirst=True)
    sa.Enum(name='projectdiscoveryresultstatus').drop(bind, checkfirst=True)
    sa.Enum(name='projectdiscoveryrunstatus').drop(bind, checkfirst=True)
    sa.Enum(name='projectdiscoveryruntype').drop(bind, checkfirst=True)
