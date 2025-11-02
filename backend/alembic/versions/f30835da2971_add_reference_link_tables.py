"""add_reference_link_tables

Revision ID: f30835da2971
Revises: 56d5d8e02d62
Create Date: 2025-09-20 11:50:25.578388

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f30835da2971'
down_revision: Union[str, None] = '56d5d8e02d62'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    project_reference_status = postgresql.ENUM('pending', 'approved', 'rejected', name='projectreferencestatus')
    project_reference_status.create(op.get_bind(), checkfirst=True)
    project_reference_status_col = postgresql.ENUM(
        'pending', 'approved', 'rejected', name='projectreferencestatus', create_type=False
    )

    op.create_table(
        'project_references',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('project_id', sa.UUID(), nullable=False),
        sa.Column('reference_id', sa.UUID(), nullable=False),
        sa.Column('status', project_reference_status_col, nullable=False, server_default='pending'),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('decided_by', sa.UUID(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['decided_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reference_id'], ['references.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'reference_id', name='uq_project_reference')
    )

    op.create_table(
        'paper_references',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('paper_id', sa.UUID(), nullable=False),
        sa.Column('reference_id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['paper_id'], ['research_papers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reference_id'], ['references.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('paper_id', 'reference_id', name='uq_paper_reference')
    )

    op.create_index('ix_paper_references_paper', 'paper_references', ['paper_id'])
    op.create_index('ix_paper_references_reference', 'paper_references', ['reference_id'])
    op.create_index('ix_project_references_project', 'project_references', ['project_id'])
    op.create_index('ix_project_references_reference', 'project_references', ['reference_id'])


def downgrade() -> None:
    op.drop_index('ix_project_references_reference', table_name='project_references')
    op.drop_index('ix_project_references_project', table_name='project_references')
    op.drop_index('ix_paper_references_reference', table_name='paper_references')
    op.drop_index('ix_paper_references_paper', table_name='paper_references')
    op.drop_table('paper_references')
    op.drop_table('project_references')
    op.execute('DROP TYPE IF EXISTS projectreferencestatus')
