"""Add owner_id to references and make paper_id nullable

Revision ID: refs_owner_and_nullable_paper
Revises: branch_mgmt_001
Create Date: 2025-09-05 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'refs_owner_and_nullable_paper'
down_revision = 'branch_mgmt_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Make paper_id nullable
    op.alter_column('references', 'paper_id', existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    # Add owner_id
    op.add_column('references', sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key('fk_references_owner', 'references', 'users', ['owner_id'], ['id'], ondelete='CASCADE')
    # Backfill owner_id using paper owner if possible
    op.execute(
        """
        UPDATE references r
        SET owner_id = p.owner_id
        FROM research_papers p
        WHERE r.paper_id = p.id AND r.owner_id IS NULL
        """
    )
    # Set owner_id not null after backfill
    op.alter_column('references', 'owner_id', nullable=False)


def downgrade() -> None:
    op.drop_constraint('fk_references_owner', 'references', type_='foreignkey')
    op.drop_column('references', 'owner_id')
    op.alter_column('references', 'paper_id', existing_type=postgresql.UUID(as_uuid=True), nullable=False)

