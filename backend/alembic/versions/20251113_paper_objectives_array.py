"""store paper objectives as json array

Revision ID: 20251113_paper_objectives_array
Revises: add_paper_objective
Create Date: 2025-11-12 22:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20251113_paper_objectives_array'
down_revision = 'add_paper_objective'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('research_papers', sa.Column('objectives', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.execute(
        """
        UPDATE research_papers
        SET objectives = CASE
            WHEN objective IS NULL OR btrim(objective) = '' THEN NULL
            ELSE jsonb_build_array(objective)
        END
        """
    )
    op.drop_column('research_papers', 'objective')


def downgrade() -> None:
    op.add_column('research_papers', sa.Column('objective', sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE research_papers
        SET objective = CASE
            WHEN objectives IS NULL OR jsonb_array_length(objectives) = 0 THEN NULL
            ELSE objectives->>0
        END
        """
    )
    op.drop_column('research_papers', 'objectives')
