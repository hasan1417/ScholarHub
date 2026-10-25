"""Add indexes for queried and cascading foreign keys.

Revision ID: 20260831_fk_query_indexes
Revises: 20260415_add_paper_abstracts_cache
Create Date: 2026-08-31
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op


revision: str = "20260831_fk_query_indexes"
down_revision: Union[str, None] = "20260415_add_paper_abstracts_cache"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


IndexSpec = tuple[str, str, tuple[str, ...]]


INDEXES: tuple[IndexSpec, ...] = (
    ("ix_ai_artifacts_project", "ai_artifacts", ("project_id",)),
    ("ix_ai_artifacts_paper", "ai_artifacts", ("paper_id",)),
    ("ix_ai_chat_sessions_user_id", "ai_chat_sessions", ("user_id",)),
    (
        "ix_ai_artifact_channel_links_channel",
        "ai_artifact_channel_links",
        ("channel_id",),
    ),
    ("ix_branches_paper_id", "branches", ("paper_id",)),
    ("ix_branches_author_id", "branches", ("author_id",)),
    ("ix_comments_paper_id", "comments", ("paper_id",)),
    ("ix_comments_commit_id", "comments", ("commit_id",)),
    ("ix_commits_branch_id", "commits", ("branch_id",)),
    ("ix_commits_author_id", "commits", ("author_id",)),
    (
        "ix_discussion_artifacts_channel_id",
        "discussion_artifacts",
        ("channel_id",),
    ),
    ("ix_document_chunks_document_id", "document_chunks", ("document_id",)),
    ("ix_document_chunks_reference_id", "document_chunks", ("reference_id",)),
    (
        "ix_document_snapshots_paper_created",
        "document_snapshots",
        ("paper_id", "created_at"),
    ),
    (
        "ix_document_snapshots_paper_sequence",
        "document_snapshots",
        ("paper_id", "sequence_number"),
    ),
    ("ix_documents_owner_id", "documents", ("owner_id",)),
    ("ix_documents_paper_id", "documents", ("paper_id",)),
    (
        "ix_editor_chat_messages_user_paper_created_at",
        "editor_chat_messages",
        ("user_id", "paper_id", "created_at"),
    ),
    ("ix_embedding_jobs_project_id", "embedding_jobs", ("project_id",)),
    ("ix_meetings_project", "meetings", ("project_id",)),
    (
        "ix_merge_requests_source_branch_id",
        "merge_requests",
        ("source_branch_id",),
    ),
    (
        "ix_merge_requests_target_branch_id",
        "merge_requests",
        ("target_branch_id",),
    ),
    ("ix_merge_requests_paper_id", "merge_requests", ("paper_id",)),
    ("ix_merge_requests_author_id", "merge_requests", ("author_id",)),
    ("ix_notifications_user", "notifications", ("user_id",)),
    ("ix_notifications_project", "notifications", ("project_id",)),
    ("ix_paper_members_paper_id", "paper_members", ("paper_id",)),
    ("ix_paper_members_user_id", "paper_members", ("user_id",)),
    (
        "ix_paper_references_reference",
        "paper_references",
        ("reference_id",),
    ),
    ("ix_paper_versions_paper_id", "paper_versions", ("paper_id",)),
    (
        "ix_pending_invitations_project_id",
        "pending_invitations",
        ("project_id",),
    ),
    (
        "ix_project_discovery_results_run_id",
        "project_discovery_results",
        ("run_id",),
    ),
    (
        "ix_project_discovery_results_reference",
        "project_discovery_results",
        ("reference_id",),
    ),
    (
        "ix_project_discovery_runs_project",
        "project_discovery_runs",
        ("project_id",),
    ),
    (
        "ix_project_discussion_assistant_exchanges_project_id",
        "project_discussion_assistant_exchanges",
        ("project_id",),
    ),
    (
        "ix_discussion_assistant_channel_created",
        "project_discussion_assistant_exchanges",
        ("channel_id", "created_at"),
    ),
    (
        "ix_discussion_assistant_author",
        "project_discussion_assistant_exchanges",
        ("author_id",),
    ),
    (
        "ix_project_discussion_channel_resources_channel",
        "project_discussion_channel_resources",
        ("channel_id",),
    ),
    (
        "ix_project_discussion_channel_resources_paper_id",
        "project_discussion_channel_resources",
        ("paper_id",),
    ),
    (
        "ix_project_discussion_channel_resources_reference_id",
        "project_discussion_channel_resources",
        ("reference_id",),
    ),
    (
        "ix_project_discussion_channel_resources_meeting_id",
        "project_discussion_channel_resources",
        ("meeting_id",),
    ),
    (
        "ix_discussion_embeddings_project",
        "project_discussion_embeddings",
        ("project_id",),
    ),
    (
        "ix_discussion_embeddings_channel",
        "project_discussion_embeddings",
        ("channel_id",),
    ),
    (
        "ix_project_discussion_message_attachments_message",
        "project_discussion_message_attachments",
        ("message_id",),
    ),
    (
        "ix_project_discussion_messages_project_id",
        "project_discussion_messages",
        ("project_id",),
    ),
    (
        "ix_project_discussion_messages_channel_created",
        "project_discussion_messages",
        ("channel_id", "created_at"),
    ),
    (
        "ix_project_discussion_messages_user_id",
        "project_discussion_messages",
        ("user_id",),
    ),
    (
        "ix_project_discussion_messages_parent_id",
        "project_discussion_messages",
        ("parent_id",),
    ),
    (
        "ix_project_discussion_tasks_project",
        "project_discussion_tasks",
        ("project_id",),
    ),
    (
        "ix_project_discussion_tasks_channel",
        "project_discussion_tasks",
        ("channel_id",),
    ),
    ("ix_project_members_project", "project_members", ("project_id",)),
    ("ix_project_members_user", "project_members", ("user_id",)),
    (
        "ix_project_references_reference",
        "project_references",
        ("reference_id",),
    ),
    (
        "ix_project_references_added_via_channel_id",
        "project_references",
        ("added_via_channel_id",),
    ),
    (
        "ix_project_sync_messages_session",
        "project_sync_messages",
        ("session_id",),
    ),
    (
        "ix_project_sync_sessions_project",
        "project_sync_sessions",
        ("project_id",),
    ),
    ("ix_projects_created_by", "projects", ("created_by",)),
    ("ix_references_owner_id", "references", ("owner_id",)),
    ("ix_references_paper_id", "references", ("paper_id",)),
    ("ix_references_document_id", "references", ("document_id",)),
    (
        "ix_research_papers_project_id",
        "research_papers",
        ("project_id",),
    ),
    ("ix_research_papers_owner_id", "research_papers", ("owner_id",)),
    (
        "ix_section_locks_paper_section",
        "section_locks",
        ("paper_id", "section_key"),
    ),
)


# These names did not exist in the migration chain at down_revision. Indexes that
# repair an earlier revision are intentionally retained by downgrade because the
# schema at down_revision already expects them to exist.
NEW_INDEX_NAMES = frozenset(
    {
        "ix_ai_chat_sessions_user_id",
        "ix_document_chunks_document_id",
        "ix_document_chunks_reference_id",
        "ix_documents_owner_id",
        "ix_documents_paper_id",
        "ix_embedding_jobs_project_id",
        "ix_merge_requests_source_branch_id",
        "ix_merge_requests_target_branch_id",
        "ix_paper_members_paper_id",
        "ix_paper_members_user_id",
        "ix_paper_versions_paper_id",
        "ix_pending_invitations_project_id",
        "ix_project_discovery_results_run_id",
        "ix_project_discussion_assistant_exchanges_project_id",
        "ix_project_discussion_channel_resources_paper_id",
        "ix_project_discussion_channel_resources_reference_id",
        "ix_project_discussion_channel_resources_meeting_id",
        "ix_projects_created_by",
        "ix_references_owner_id",
        "ix_references_paper_id",
        "ix_references_document_id",
        "ix_research_papers_owner_id",
    }
)


def _create_index_sql(name: str, table: str, columns: tuple[str, ...]) -> str:
    return f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON {table} ({', '.join(columns)})"


def upgrade() -> None:
    # PostgreSQL forbids CREATE INDEX CONCURRENTLY inside a transaction block.
    with op.get_context().autocommit_block():
        for name, table, columns in INDEXES:
            op.execute(_create_index_sql(name, table, columns))


def downgrade() -> None:
    with op.get_context().autocommit_block():
        for name, _, _ in reversed(INDEXES):
            if name in NEW_INDEX_NAMES:
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {name}")
