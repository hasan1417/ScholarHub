"""create latex_crdt_snapshots table

Revision ID: add_latex_crdt_snapshots
Revises: dedupe_references_and_add_uniques
Create Date: 2025-09-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_latex_crdt_snapshots'
down_revision = 'dedupe_references_and_add_uniques'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'latex_crdt_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('paper_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('research_papers.id'), nullable=False),
        sa.Column('branch_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('branches.id'), nullable=True),
        sa.Column('rev', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('state', sa.LargeBinary(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_latex_crdt_snapshots_paper_id', 'latex_crdt_snapshots', ['paper_id'])
    op.create_index('ix_latex_crdt_snapshots_branch_id', 'latex_crdt_snapshots', ['branch_id'])
    op.create_index('ix_latex_crdt_snapshots_created_at', 'latex_crdt_snapshots', ['created_at'])


def downgrade() -> None:
    op.drop_index('ix_latex_crdt_snapshots_created_at', table_name='latex_crdt_snapshots')
    op.drop_index('ix_latex_crdt_snapshots_branch_id', table_name='latex_crdt_snapshots')
    op.drop_index('ix_latex_crdt_snapshots_paper_id', table_name='latex_crdt_snapshots')
    op.drop_table('latex_crdt_snapshots')

