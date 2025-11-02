"""add multichannel discussion structures

Revision ID: 4b2f2cb03b75
Revises: 1ac5270db9ab
Create Date: 2025-10-05 00:00:00.000000

"""
from __future__ import annotations

import uuid
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "4b2f2cb03b75"
down_revision: Union[str, None] = "1ac5270db9ab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


ATTACHMENT_ENUM_NAME = "projectdiscussionattachmenttype"
RESOURCE_ENUM_NAME = "projectdiscussionresourcetype"
TASK_STATUS_ENUM_NAME = "projectdiscussiontaskstatus"


def upgrade() -> None:
    op.create_table(
        "project_discussion_channels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("project_id", "slug", name="uq_discussion_channel_project_slug"),
    )

    op.create_index(
        "ix_project_discussion_channels_project_id",
        "project_discussion_channels",
        ["project_id"],
    )
    op.create_index(
        "ix_project_discussion_channels_slug",
        "project_discussion_channels",
        ["slug"],
    )
    op.create_index(
        "uq_project_discussion_default_channel",
        "project_discussion_channels",
        ["project_id"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )

    op.add_column(
        "project_discussion_messages",
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_project_discussion_messages_channel",
        "project_discussion_messages",
        "project_discussion_channels",
        ["channel_id"],
        ["id"],
        ondelete="CASCADE",
    )

    projects_table = sa.table(
        "projects",
        sa.column("id", postgresql.UUID(as_uuid=True)),
    )
    channels_table = sa.table(
        "project_discussion_channels",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("project_id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("slug", sa.String),
        sa.column("is_default", sa.Boolean),
        sa.column("is_archived", sa.Boolean),
    )

    connection = op.get_bind()
    project_ids = [row[0] for row in connection.execute(sa.select(projects_table.c.id))]

    for project_id in project_ids:
        channel_id = uuid.uuid4()
        connection.execute(
            channels_table.insert().values(
                id=channel_id,
                project_id=project_id,
                name="General",
                slug="general",
                is_default=True,
                is_archived=False,
            )
        )
        connection.execute(
            sa.text(
                "UPDATE project_discussion_messages "
                "SET channel_id = :channel_id "
                "WHERE project_id = :project_id"
            ),
            {"channel_id": str(channel_id), "project_id": str(project_id)},
        )

    op.alter_column(
        "project_discussion_messages",
        "channel_id",
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
    )

    op.create_index(
        "ix_project_discussion_messages_channel_id",
        "project_discussion_messages",
        ["channel_id"],
    )
    op.create_index(
        "ix_project_discussion_messages_channel_created",
        "project_discussion_messages",
        ["channel_id", "created_at"],
    )

    op.create_table(
        "project_discussion_channel_resources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "resource_type",
            sa.String(length=16),
            nullable=False,
        ),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_papers.id", ondelete="CASCADE"), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("references.id", ondelete="CASCADE"), nullable=True),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("meetings.id", ondelete="CASCADE"), nullable=True),
        sa.Column("external_url", sa.String(length=1000), nullable=True),
        sa.Column("tag", sa.String(length=100), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.CheckConstraint(
            "("  # ensure target matches type
            "(resource_type = 'paper' AND paper_id IS NOT NULL AND reference_id IS NULL AND meeting_id IS NULL AND tag IS NULL AND external_url IS NULL)"
            " OR "
            "(resource_type = 'reference' AND reference_id IS NOT NULL AND paper_id IS NULL AND meeting_id IS NULL AND tag IS NULL AND external_url IS NULL)"
            " OR "
            "(resource_type = 'meeting' AND meeting_id IS NOT NULL AND paper_id IS NULL AND reference_id IS NULL AND tag IS NULL AND external_url IS NULL)"
            " OR "
            "(resource_type = 'tag' AND tag IS NOT NULL AND paper_id IS NULL AND reference_id IS NULL AND meeting_id IS NULL AND external_url IS NULL)"
            " OR "
            "(resource_type = 'external' AND external_url IS NOT NULL AND paper_id IS NULL AND reference_id IS NULL AND meeting_id IS NULL AND tag IS NULL)"
            ")",
            name="ck_discussion_channel_resource_target",
        ),
    )
    op.create_index(
        "ix_project_discussion_channel_resources_channel",
        "project_discussion_channel_resources",
        ["channel_id"],
    )

    op.create_table(
        "project_discussion_message_attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_discussion_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("attachment_type", sa.String(length=16), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("paper_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("research_papers.id", ondelete="SET NULL"), nullable=True),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("references.id", ondelete="SET NULL"), nullable=True),
        sa.Column("meeting_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.CheckConstraint(
            "document_id IS NOT NULL OR paper_id IS NOT NULL OR reference_id IS NOT NULL OR meeting_id IS NOT NULL OR url IS NOT NULL",
            name="ck_discussion_message_attachment_has_target",
        ),
    )
    op.create_index(
        "ix_project_discussion_message_attachments_message",
        "project_discussion_message_attachments",
        ["message_id"],
    )

    op.create_table(
        "project_discussion_tasks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_discussion_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="open"),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_index(
        "ix_project_discussion_tasks_project",
        "project_discussion_tasks",
        ["project_id"],
    )
    op.create_index(
        "ix_project_discussion_tasks_channel",
        "project_discussion_tasks",
        ["channel_id"],
    )
    op.create_index(
        "ix_project_discussion_tasks_status",
        "project_discussion_tasks",
        ["status"],
    )

    op.create_table(
        "ai_artifact_channel_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_artifacts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("channel_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_discussion_channels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("project_discussion_messages.id", ondelete="SET NULL"), nullable=True),
        sa.Column("linked_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("context_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("artifact_id", "channel_id", name="uq_ai_artifact_channel"),
    )
    op.create_index(
        "ix_ai_artifact_channel_links_channel",
        "ai_artifact_channel_links",
        ["channel_id"],
    )
    op.create_index(
        "ix_ai_artifact_channel_links_artifact",
        "ai_artifact_channel_links",
        ["artifact_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_ai_artifact_channel_links_artifact", table_name="ai_artifact_channel_links")
    op.drop_index("ix_ai_artifact_channel_links_channel", table_name="ai_artifact_channel_links")
    op.drop_table("ai_artifact_channel_links")

    op.drop_index("ix_project_discussion_tasks_status", table_name="project_discussion_tasks")
    op.drop_index("ix_project_discussion_tasks_channel", table_name="project_discussion_tasks")
    op.drop_index("ix_project_discussion_tasks_project", table_name="project_discussion_tasks")
    op.drop_table("project_discussion_tasks")

    op.drop_index(
        "ix_project_discussion_message_attachments_message",
        table_name="project_discussion_message_attachments",
    )
    op.drop_table("project_discussion_message_attachments")

    op.drop_index(
        "ix_project_discussion_channel_resources_channel",
        table_name="project_discussion_channel_resources",
    )
    op.drop_table("project_discussion_channel_resources")

    op.drop_index(
        "ix_project_discussion_messages_channel_created",
        table_name="project_discussion_messages",
    )
    op.drop_index(
        "ix_project_discussion_messages_channel_id",
        table_name="project_discussion_messages",
    )

    op.drop_constraint(
        "fk_project_discussion_messages_channel",
        "project_discussion_messages",
        type_="foreignkey",
    )
    op.drop_column("project_discussion_messages", "channel_id")

    op.drop_index("uq_project_discussion_default_channel", table_name="project_discussion_channels")
    op.drop_index("ix_project_discussion_channels_slug", table_name="project_discussion_channels")
    op.drop_index("ix_project_discussion_channels_project_id", table_name="project_discussion_channels")
    op.drop_table("project_discussion_channels")

    bind = op.get_bind()
    sa.Enum(name=ATTACHMENT_ENUM_NAME).drop(bind, checkfirst=True)
    sa.Enum(name=RESOURCE_ENUM_NAME).drop(bind, checkfirst=True)
    sa.Enum(name=TASK_STATUS_ENUM_NAME).drop(bind, checkfirst=True)
