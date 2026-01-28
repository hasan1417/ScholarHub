"""add_unique_constraint_channel_name

Revision ID: 4138c3e33bbc
Revises: d0446baeb1ff
Create Date: 2026-01-28 13:05:21.966895

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4138c3e33bbc'
down_revision: Union[str, None] = 'd0446baeb1ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # First, handle any existing duplicates by appending a number suffix
    # This ensures the constraint can be created
    conn = op.get_bind()

    # Find duplicates: channels with same project_id and name
    duplicates = conn.execute(sa.text("""
        SELECT id, project_id, name,
               ROW_NUMBER() OVER (PARTITION BY project_id, name ORDER BY created_at) as rn
        FROM project_discussion_channels
    """)).fetchall()

    # Rename duplicates (rn > 1 means it's a duplicate)
    for row in duplicates:
        if row.rn > 1:
            new_name = f"{row.name} ({row.rn})"
            conn.execute(
                sa.text("UPDATE project_discussion_channels SET name = :new_name WHERE id = :id"),
                {"new_name": new_name, "id": row.id}
            )

    # Now add the unique constraint
    op.create_unique_constraint(
        'uq_discussion_channel_project_name',
        'project_discussion_channels',
        ['project_id', 'name']
    )


def downgrade() -> None:
    op.drop_constraint('uq_discussion_channel_project_name', 'project_discussion_channels', type_='unique')
