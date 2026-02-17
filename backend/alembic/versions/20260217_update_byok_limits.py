"""Update BYOK tier to Pro-level resource limits with unlimited references.

Revision ID: 20260217_byok_limits
Revises: 20260217_pdf_annotations
Create Date: 2026-02-17

BYOK users bring their own API key (saving us AI costs), so they should get
Pro-level non-AI limits. References set to unlimited (-1) since DB rows are cheap
and power users easily exceed 500.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "20260217_byok_limits"
down_revision: Union[str, None] = "20260217_pdf_annotations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
        UPDATE subscription_tiers
        SET limits = '{
            "discussion_ai_calls": -1,
            "editor_ai_calls": -1,
            "paper_discovery_searches": -1,
            "projects": 25,
            "papers_per_project": 100,
            "collaborators_per_project": 10,
            "references_total": -1
        }'
        WHERE id = 'byok'
    """)


def downgrade() -> None:
    op.execute("""
        UPDATE subscription_tiers
        SET limits = '{
            "discussion_ai_calls": -1,
            "paper_discovery_searches": -1,
            "projects": 10,
            "papers_per_project": 50,
            "collaborators_per_project": 5,
            "references_total": 200
        }'
        WHERE id = 'byok'
    """)
