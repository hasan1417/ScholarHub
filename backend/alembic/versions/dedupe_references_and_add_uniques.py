"""Deduplicate references and add uniqueness constraints

Revision ID: dedupe_references_and_add_uniques
Revises: add_reference_id_to_document_chunks
Create Date: 2025-09-08 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
import uuid as _uuid
import re as _re

# revision identifiers, used by Alembic.
revision = 'dedupe_references_and_add_uniques'
down_revision = 'add_reference_id_to_document_chunks'
branch_labels = None
depends_on = None


def _normalize_title(s: str) -> str:
    if not s:
        return ''
    # collapse whitespace and lowercase
    return _re.sub(r"\s+", " ", s.strip()).lower()


def upgrade():
    bind = op.get_bind()

    # 1) Deduplicate by DOI (within same owner_id + paper_id)
    # fetch all references with non-null doi
    rows = bind.execute(text(
        'SELECT id, owner_id, paper_id, doi, created_at, document_id '
        'FROM "references" WHERE doi IS NOT NULL'
    )).mappings().all()

    groups = {}
    for r in rows:
        key = (str(r['owner_id']), str(r['paper_id']) if r['paper_id'] is not None else '00000000-0000-0000-0000-000000000000', (r['doi'] or '').strip().lower())
        groups.setdefault(key, []).append(r)

    for key, items in groups.items():
        if len(items) <= 1:
            continue
        # choose canonical: oldest created_at then smallest id
        items_sorted = sorted(items, key=lambda x: (x['created_at'] or 0, str(x['id'])))
        canonical = items_sorted[0]
        dupe_ids = [i['id'] for i in items_sorted[1:]]
        if not dupe_ids:
            continue
        # Point document_chunks to canonical
        bind.execute(text(
            'UPDATE document_chunks SET reference_id = :canon '
            'WHERE reference_id = ANY(:dupes)'
        ), {"canon": str(canonical['id']), "dupes": dupe_ids})
        # If canonical has no document_id, adopt first available from duplicates
        if canonical['document_id'] is None:
            doc_row = bind.execute(text(
                'SELECT document_id FROM "references" WHERE id = ANY(:dupes) AND document_id IS NOT NULL LIMIT 1'
            ), {"dupes": dupe_ids}).first()
            if doc_row and doc_row[0]:
                bind.execute(text('UPDATE "references" SET document_id = :doc WHERE id = :id'), {"doc": str(doc_row[0]), "id": str(canonical['id'])})
        # Delete duplicates
        bind.execute(text('DELETE FROM "references" WHERE id = ANY(:dupes)'), {"dupes": dupe_ids})

    # 2) Deduplicate by normalized title + year when DOI is NULL (within owner_id + paper_id)
    rows2 = bind.execute(text(
        'SELECT id, owner_id, paper_id, title, year, created_at, document_id '
        'FROM "references" WHERE doi IS NULL'
    )).mappings().all()

    groups2 = {}
    for r in rows2:
        norm_title = _normalize_title(r['title'])
        year_key = r['year'] if r['year'] is not None else 0
        key = (str(r['owner_id']), str(r['paper_id']) if r['paper_id'] is not None else '00000000-0000-0000-0000-000000000000', norm_title, year_key)
        groups2.setdefault(key, []).append(r)

    for key, items in groups2.items():
        if len(items) <= 1:
            continue
        items_sorted = sorted(items, key=lambda x: (x['created_at'] or 0, str(x['id'])))
        canonical = items_sorted[0]
        dupe_ids = [i['id'] for i in items_sorted[1:]]
        if not dupe_ids:
            continue
        bind.execute(text(
            'UPDATE document_chunks SET reference_id = :canon '
            'WHERE reference_id = ANY(:dupes)'
        ), {"canon": str(canonical['id']), "dupes": dupe_ids})
        if canonical['document_id'] is None:
            doc_row = bind.execute(text(
                'SELECT document_id FROM "references" WHERE id = ANY(:dupes) AND document_id IS NOT NULL LIMIT 1'
            ), {"dupes": dupe_ids}).first()
            if doc_row and doc_row[0]:
                bind.execute(text('UPDATE "references" SET document_id = :doc WHERE id = :id'), {"doc": str(doc_row[0]), "id": str(canonical['id'])})
        bind.execute(text('DELETE FROM "references" WHERE id = ANY(:dupes)'), {"dupes": dupe_ids})

    # 3) Add uniqueness constraints via partial unique indexes
    # 3a) Unique per (owner_id, paper_id, lower(doi)) when doi is not null
    op.execute(text(
        'CREATE UNIQUE INDEX IF NOT EXISTS uq_refs_owner_paper_doi '
        'ON "references" (owner_id, COALESCE(paper_id, :null_uuid::uuid), lower(doi)) '
        'WHERE doi IS NOT NULL'
    ).bindparams(null_uuid='00000000-0000-0000-0000-000000000000'))

    # 3b) Unique per (owner_id, paper_id, normalized_title, year) when doi is null
    op.execute(text(r"""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_refs_owner_paper_title_year_nodoi
        ON "references" (
            owner_id,
            COALESCE(paper_id, :null_uuid::uuid),
            lower(regexp_replace(title, '\\s+', ' ', 'g')),
            COALESCE(year, 0)
        ) WHERE doi IS NULL
    """).bindparams(null_uuid='00000000-0000-0000-0000-000000000000'))


def downgrade():
    # Drop unique indexes (cannot reverse deduplication)
    op.execute('DROP INDEX IF EXISTS uq_refs_owner_paper_doi')
    op.execute('DROP INDEX IF EXISTS uq_refs_owner_paper_title_year_nodoi')
