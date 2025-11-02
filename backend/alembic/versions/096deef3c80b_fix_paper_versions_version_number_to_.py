"""fix paper_versions version_number to string

Revision ID: 096deef3c80b
Revises: add_section_locks_table
Create Date: 2025-09-18 15:07:20.735266

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '096deef3c80b'
down_revision: Union[str, None] = 'add_section_locks_table'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Change version_number from INTEGER to VARCHAR(50) to support semantic versioning
    op.alter_column('paper_versions', 'version_number',
               existing_type=sa.INTEGER(),
               type_=sa.String(length=50),
               existing_nullable=False)


def downgrade() -> None:
    # Revert version_number back to INTEGER
    op.alter_column('paper_versions', 'version_number',
               existing_type=sa.String(length=50),
               type_=sa.INTEGER(),
               existing_nullable=False)
