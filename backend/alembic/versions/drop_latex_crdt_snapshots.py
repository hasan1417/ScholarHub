"""drop latex_crdt_snapshots table

Revision ID: drop_latex_crdt_snapshots
Revises: add_comments_table
Create Date: 2025-09-10 12:30:00.000000

"""
from alembic import op


# revision identifiers, used by Alembic.
revision = 'drop_latex_crdt_snapshots'
down_revision = 'migrate_crdt_to_versions'
branch_labels = None
depends_on = None


def upgrade():
    try:
        op.drop_table('latex_crdt_snapshots')
    except Exception:
        # Table may already be dropped; ignore
        pass


def downgrade():
    # No automatic recreation to avoid restoring deprecated feature
    pass
