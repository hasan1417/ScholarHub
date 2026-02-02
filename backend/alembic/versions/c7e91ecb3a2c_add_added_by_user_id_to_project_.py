"""add_added_by_user_id_to_project_references

Revision ID: c7e91ecb3a2c
Revises: 20260129_encrypt_openrouter_api_key
Create Date: 2026-02-01 20:49:27.807066

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'c7e91ecb3a2c'
down_revision: Union[str, None] = '20260129_encrypt_openrouter_api_key'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add added_by_user_id column to track who added each reference
    op.add_column(
        'project_references',
        sa.Column('added_by_user_id', sa.UUID(), nullable=True)
    )
    op.create_foreign_key(
        'fk_project_references_added_by_user_id',
        'project_references',
        'users',
        ['added_by_user_id'],
        ['id'],
        ondelete='SET NULL'
    )
    # Add index for efficient lookups by user
    op.create_index(
        'ix_project_references_added_by_user_id',
        'project_references',
        ['added_by_user_id']
    )


def downgrade() -> None:
    op.drop_index('ix_project_references_added_by_user_id', table_name='project_references')
    op.drop_constraint('fk_project_references_added_by_user_id', 'project_references', type_='foreignkey')
    op.drop_column('project_references', 'added_by_user_id')
