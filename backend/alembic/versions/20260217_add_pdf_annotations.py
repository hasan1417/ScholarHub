"""Add pdf_annotations table

Revision ID: 20260217_pdf_annotations
Revises: cde91bc9dba9
Create Date: 2026-02-17

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "20260217_pdf_annotations"
down_revision: Union[str, None] = "cde91bc9dba9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pdf_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("color", sa.String(7), server_default="#FFEB3B"),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("position_data", postgresql.JSONB(), nullable=False),
        sa.Column("selected_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )

    op.create_index("ix_pdf_annotations_document_id", "pdf_annotations", ["document_id"])
    op.create_index("ix_pdf_annotations_user_id", "pdf_annotations", ["user_id"])
    op.create_index("ix_pdf_annotations_document_user", "pdf_annotations", ["document_id", "user_id"])
    op.create_index("ix_pdf_annotations_document_page", "pdf_annotations", ["document_id", "page_number"])


def downgrade() -> None:
    op.drop_index("ix_pdf_annotations_document_page", table_name="pdf_annotations")
    op.drop_index("ix_pdf_annotations_document_user", table_name="pdf_annotations")
    op.drop_index("ix_pdf_annotations_user_id", table_name="pdf_annotations")
    op.drop_index("ix_pdf_annotations_document_id", table_name="pdf_annotations")
    op.drop_table("pdf_annotations")
