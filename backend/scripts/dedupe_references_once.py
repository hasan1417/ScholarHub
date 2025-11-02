import os
from sqlalchemy import create_engine, text
from collections import defaultdict
import re


def normalize_title(s: str) -> str:
    if not s:
        return ''
    return re.sub(r"\s+", " ", s.strip()).lower()


def main():
    db_url = os.getenv('DATABASE_URL', 'postgresql://scholarhub:scholarhub@localhost:5432/scholarhub')
    engine = create_engine(db_url)
    with engine.begin() as conn:
        # 1) Deduplicate by DOI within (owner_id, paper_id)
        rows = conn.execute(text(
            'SELECT id::text AS id, owner_id::text AS owner_id, '
            'COALESCE(paper_id::text, :null_uuid) AS paper_id, '
            'lower(doi) AS doi, created_at, document_id::text AS document_id '
            'FROM "references" WHERE doi IS NOT NULL'
        ), {"null_uuid": '00000000-0000-0000-0000-000000000000'}).mappings().all()

        groups = defaultdict(list)
        for r in rows:
            groups[(r['owner_id'], r['paper_id'], r['doi'] or '')].append(r)

        merged_by_doi = 0
        for key, items in groups.items():
            if len(items) <= 1:
                continue
            items_sorted = sorted(items, key=lambda x: (x['created_at'] or 0, x['id']))
            canonical = items_sorted[0]
            dupes = [i['id'] for i in items_sorted[1:]]
            if not dupes:
                continue
            # Repoint chunks
            for dupe in dupes:
                conn.execute(text('UPDATE document_chunks SET reference_id = :canon WHERE reference_id::text = :dupe'),
                             {"canon": canonical['id'], "dupe": dupe})
            # Adopt document if missing
            if canonical['document_id'] is None:
                doc_row = None
                for dupe in dupes:
                    r = conn.execute(text('SELECT document_id::text FROM "references" WHERE id::text = :id AND document_id IS NOT NULL LIMIT 1'), {"id": dupe}).first()
                    if r and r[0]:
                        doc_row = r
                        break
                if doc_row and doc_row[0]:
                    conn.execute(text('UPDATE "references" SET document_id = :doc WHERE id = :id'),
                                 {"doc": doc_row[0], "id": canonical['id']})
            # Delete dupes
            for dupe in dupes:
                conn.execute(text('DELETE FROM "references" WHERE id::text = :id'), {"id": dupe})
            merged_by_doi += len(dupes)

        # 2) Deduplicate by normalized title+year when DOI is NULL
        rows2 = conn.execute(text(
            'SELECT id::text AS id, owner_id::text AS owner_id, '
            'COALESCE(paper_id::text, :null_uuid) AS paper_id, '
            'title, COALESCE(year, 0) AS year, created_at, document_id::text AS document_id '
            'FROM "references" WHERE doi IS NULL'
        ), {"null_uuid": '00000000-0000-0000-0000-000000000000'}).mappings().all()

        groups2 = defaultdict(list)
        for r in rows2:
            key = (r['owner_id'], r['paper_id'], normalize_title(r['title']), int(r['year'] or 0))
            groups2[key].append(r)

        merged_by_title = 0
        for key, items in groups2.items():
            if len(items) <= 1:
                continue
            items_sorted = sorted(items, key=lambda x: (x['created_at'] or 0, x['id']))
            canonical = items_sorted[0]
            dupes = [i['id'] for i in items_sorted[1:]]
            if not dupes:
                continue
            for dupe in dupes:
                conn.execute(text('UPDATE document_chunks SET reference_id = :canon WHERE reference_id::text = :dupe'),
                             {"canon": canonical['id'], "dupe": dupe})
            if canonical['document_id'] is None:
                doc_row = None
                for dupe in dupes:
                    r = conn.execute(text('SELECT document_id::text FROM "references" WHERE id::text = :id AND document_id IS NOT NULL LIMIT 1'), {"id": dupe}).first()
                    if r and r[0]:
                        doc_row = r
                        break
                if doc_row and doc_row[0]:
                    conn.execute(text('UPDATE "references" SET document_id = :doc WHERE id = :id'),
                                 {"doc": doc_row[0], "id": canonical['id']})
            for dupe in dupes:
                conn.execute(text('DELETE FROM "references" WHERE id::text = :id'), {"id": dupe})
            merged_by_title += len(dupes)

        # 3) Create unique indexes to prevent future duplicates
        conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_refs_owner_paper_doi
            ON "references" (owner_id, COALESCE(paper_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(doi))
            WHERE doi IS NOT NULL
        """))

        conn.execute(text(r'''
            CREATE UNIQUE INDEX IF NOT EXISTS uq_refs_owner_paper_title_year_nodoi
            ON "references" (
                owner_id,
                COALESCE(paper_id, '00000000-0000-0000-0000-000000000000'::uuid),
                lower(regexp_replace(title, '\s+', ' ', 'g')),
                COALESCE(year, 0)
            ) WHERE doi IS NULL
        '''))

    print("Deduplication completed. Merged by DOI and title/year. Unique indexes created.")


if __name__ == '__main__':
    main()
