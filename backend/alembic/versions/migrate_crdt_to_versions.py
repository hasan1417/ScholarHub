"""migrate crdt snapshots to branch commits

Revision ID: migrate_crdt_to_versions
Revises: add_comments_table
Create Date: 2025-09-10 13:05:00.000000

"""
from alembic import op
from sqlalchemy import text
import uuid


# revision identifiers, used by Alembic.
revision = 'migrate_crdt_to_versions'
# Merge point: requires both comments and snapshots branches
down_revision = ('add_comments_table', 'add_latex_crdt_snapshots')
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # Check if snapshots table exists; skip if not
    try:
        res = conn.execute(text("SELECT to_regclass('public.latex_crdt_snapshots')"))
        exists = res.scalar()
    except Exception:
        exists = None
    if not exists:
        return

    # Collect latest snapshot per paper_id
    rows = conn.execute(text(
        """
        SELECT DISTINCT ON (paper_id) paper_id, rev, state
        FROM latex_crdt_snapshots
        ORDER BY paper_id, rev DESC
        """
    )).fetchall()
    if not rows:
        return

    # Helper: materialize text from Yjs update using y_py if available
    def ydoc_to_text(update_bytes: bytes) -> str:
        try:
            from y_py import YDoc  # type: ignore
        except Exception:
            return ''
        try:
            with YDoc() as ydoc:  # type: ignore
                ydoc.apply_update(update_bytes)  # type: ignore[attr-defined]
                ytext = ydoc.get_text('latex')  # type: ignore[attr-defined]
                try:
                    return str(ytext)
                except Exception:
                    try:
                        return ytext.to_string()  # type: ignore[attr-defined]
                    except Exception:
                        return ''
        except Exception:
            return ''

    for r in rows:
        paper_id = r[0]
        update_state = bytes(r[2]) if r[2] is not None else b''
        latex = ydoc_to_text(update_state)
        if latex is None:
            latex = ''

        # Find or create main branch and paper owner
        paper = conn.execute(text("SELECT id, owner_id FROM research_papers WHERE id = :pid"), { 'pid': paper_id }).fetchone()
        if not paper:
            continue
        owner_id = paper[1]
        br = conn.execute(text("SELECT id FROM branches WHERE paper_id = :pid AND name = 'main'"), { 'pid': paper_id }).fetchone()
        if not br:
            # create branch with generated UUID
            bid = str(uuid.uuid4())
            conn.execute(text("INSERT INTO branches (id, name, paper_id, author_id, is_main) VALUES (:id, 'main', :pid, :uid, true)"), { 'id': bid, 'pid': paper_id, 'uid': owner_id })
            br = (bid,)
        branch_id = br[0]

        # Insert commit if not exists with message marker
        cid = str(uuid.uuid4())
        conn.execute(text(
            """
            INSERT INTO commits (id, branch_id, message, content, content_json, author_id, changes, compilation_status, state)
            VALUES (:id, :branch_id, :message, :content, :content_json, :author_id, '[]'::jsonb, 'not_compiled', 'draft')
            """
        ), {
            'id': cid,
            'branch_id': branch_id,
            'message': 'Initial (CRDT migration)',
            'content': latex or '',
            'content_json': { 'authoring_mode': 'latex', 'latex_source': latex or '' },
            'author_id': owner_id,
        })

    # Optional: clear snapshots; drop table handled in subsequent migration
    conn.execute(text("DELETE FROM latex_crdt_snapshots"))


def downgrade():
    # No-op
    pass
