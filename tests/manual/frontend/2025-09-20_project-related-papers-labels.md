# Project Related Papers Label Update

## Purpose
Confirm the Project workspace shows the "Related Papers" tab while paper detail pages retain the "References" section heading.

## Setup
- Backend running with project-first flags enabled.
- Frontend dev server on `http://localhost:3000` with an authenticated session.
- At least one project (e.g., Legacy Migration) populated with papers via the migration script.

## Test Data
- User: `g202403940@kfupm.edu.sa` / `testpass123`.

## Steps
1. Log in and open any project from the Projects home (e.g., Legacy Migration).
2. Observe the project navigation pills at the top of the workspace.
3. Click the "Related Papers" pill and confirm the landing copy references related papers.
4. From the same project, open any paper (e.g., via Papers tab → select paper) and locate the references panel in the paper detail view.

## Expected Results
- The navigation pill reads "Related Papers" (no longer "References").
- The tab content headline is "Related papers" with copy describing suggested project papers.
- Within the paper detail view, the references panel header still reads "References".

## Rollback
Revert the label changes in `frontend/src/pages/projects/ProjectLayout.tsx` and `frontend/src/pages/projects/ProjectReferences.tsx` if needed.

## Evidence
- Manual verification in browser; no screenshot captured.
