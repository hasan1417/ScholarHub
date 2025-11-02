# Project Discovery Settings

## Purpose
Validate that project owners can configure discovery preferences, trigger manual runs, and see new references flow into the suggestions queue.

## Setup
- Backend running with `PROJECT_REFERENCE_SUGGESTIONS_ENABLED=true`.
- Frontend dev server on `http://localhost:3000`.
- Account: `g202403940@kfupm.edu.sa` / `testpass123`.

## Test Data
- Legacy Migration project populated via migration script.

## Steps
1. Log in and open the Legacy Migration project.
2. In Related Papers, adjust the discovery form (query, keywords, auto toggle) and save.
3. Click **Run Discovery** and monitor the network tab for `POST /discovery/run` to confirm the request succeeds.
4. Refresh suggestions and observe any new pending references (sourced from the manual run or background jobs).

## Expected Results
- Preferences persist after saving and page refresh.
- Manual discovery exposes the run button, which successfully triggers a manual discovery cycle and updates the “Last run” timestamp.
- Any newly found references appear as pending suggestions ready for approval.

## Rollback
Reopen the form and clear/reset preferences if needed.

## Evidence
- Manual verification; no screenshot captured.
