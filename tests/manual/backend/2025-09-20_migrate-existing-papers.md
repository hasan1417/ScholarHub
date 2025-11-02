# Backfill Existing Papers Into Legacy Project

## Purpose
Confirm the migration script links all pre-existing research papers to the dummy "Legacy Migration" project so the new Projects landing has data.

## Setup
- Backend virtualenv `scholarenv` available.
- Postgres container running (`scholarhub-postgres-1`).
- Feature flags switched to project-first mode (see `backend/.env`).

## Test Data
- Existing research papers and references already present in the database.
- Dummy project owner email: `g202403940@kfupm.edu.sa`.

## Steps
1. Run `scholarenv/bin/python -m app.scripts.migrate_to_projects --dry-run --owner-email g202403940@kfupm.edu.sa` and verify the summary reports the expected paper count.
2. Execute `scholarenv/bin/python -m app.scripts.migrate_to_projects --execute --owner-email g202403940@kfupm.edu.sa` to persist the migration.
3. Query Postgres: `SELECT title, project_id FROM research_papers LIMIT 3;` to confirm each paper now points to the Legacy project.
4. Query `project_members` to verify the owner is marked as `owner` and collaborators as `editor`.

## Expected Results
- Dry-run logs the number of papers processed without committing changes.
- Execute run completes with "Migration committed" summary and no errors.
- All research papers show the same `project_id` referencing `Legacy Migration`.
- Project members table contains the owner plus all unique paper users with lowercase role values.

## Rollback
If needed, restore from a database backup prior to running the migration script.

## Evidence
- Terminal output from the migration script (dry-run and execute) confirming success.
