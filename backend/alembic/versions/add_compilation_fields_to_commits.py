"""add compilation fields to commits

Revision ID: add_compilation_fields_to_commits
Revises: branch_mgmt_001
Create Date: 2025-09-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_compilation_fields_to_commits'
down_revision = 'branch_mgmt_001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('commits', sa.Column('compilation_status', sa.String(length=20), nullable=False, server_default='not_compiled'))
    op.add_column('commits', sa.Column('pdf_url', sa.Text(), nullable=True))
    op.add_column('commits', sa.Column('compile_logs', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('commits', 'compile_logs')
    op.drop_column('commits', 'pdf_url')
    op.drop_column('commits', 'compilation_status')

