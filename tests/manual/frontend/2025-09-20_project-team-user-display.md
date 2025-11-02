# Project Team Member Display

## Purpose
Verify that project member listings show human-friendly names and emails instead of raw UUIDs after the backend now returns nested user details.

## Setup
- Backend running locally with feature flags enabled (PROJECTS_API_ENABLED, etc.).
- Frontend dev server on `http://localhost:3000`.
- Database migrated to include the Legacy Migration project with members.
- Test account: `g202403940@kfupm.edu.sa` / `testpass123`.

## Test Data
- Existing project memberships from the legacy migration script.

## Steps
1. Log in to the frontend using the test credentials.
2. Open the Legacy Migration project from the Projects home.
3. On the Overview tab, inspect the Team card.
4. Confirm each member row shows a display name (or email) plus the email on a second line and a title-cased role badge.

## Expected Results
- No UUIDs are shown; each teammate row renders a readable name (or email fallback) with their email address beneath.
- Role badges read `Owner`, `Editor`, etc., instead of uppercase values.

## Rollback
Revert the schema/type updates in `backend/app/schemas/project.py`, `backend/app/api/v1/projects.py`, and `frontend/src/pages/projects/ProjectOverview.tsx` if the change needs to be undone.

## Evidence
- Manual verification in the browser; no screenshot captured.
