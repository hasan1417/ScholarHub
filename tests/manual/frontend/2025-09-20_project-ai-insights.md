# Project AI Insights

## Purpose
Confirm the Project overview AI card lists recent artifacts and allows triggering scoped AI jobs.

## Setup
- Backend running with `PROJECT_AI_ORCHESTRATION_ENABLED=true`.
- Frontend dev server running at `http://localhost:3000`.
- Account: `g202403940@kfupm.edu.sa` / `testpass123`.

## Test Data
- Legacy Migration project (with context populated by migration).

## Steps
1. Log in and open the Legacy Migration project Overview tab.
2. Observe the AI insights card.
3. Click “Project summary” and wait for the status message to appear.
4. After the mutation completes, verify the artifact list refreshes with the new entry and shows its status/result.

## Expected Results
- AI card renders quick action buttons when the feature flag is enabled.
- Triggering an action shows a transient status message and disables buttons while pending.
- New artifact appears in the list with type, status pill, and preview text.

## Rollback
No rollback required.

## Evidence
- Manual verification; no screenshot captured.
