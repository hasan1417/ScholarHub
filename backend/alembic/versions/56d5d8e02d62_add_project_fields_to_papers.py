"""add_project_fields_to_papers

Revision ID: 56d5d8e02d62
Revises: ce3f9aca8c72
Create Date: 2025-09-20 11:50:10.582621

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '56d5d8e02d62'
down_revision: Union[str, None] = 'ce3f9aca8c72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('research_papers', sa.Column('project_id', sa.UUID(), nullable=True))
    op.add_column('research_papers', sa.Column('format', sa.String(length=50), nullable=True))
    op.add_column('research_papers', sa.Column('summary', sa.Text(), nullable=True))
    op.create_foreign_key(
        'fk_research_papers_project',
        'research_papers',
        'projects',
        ['project_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index('ix_research_papers_project_id', 'research_papers', ['project_id'])


def downgrade() -> None:
    op.drop_index('ix_research_papers_project_id', table_name='research_papers')
    op.drop_constraint('fk_research_papers_project', 'research_papers', type_='foreignkey')
    op.drop_column('research_papers', 'summary')
    op.drop_column('research_papers', 'format')
    op.drop_column('research_papers', 'project_id')
