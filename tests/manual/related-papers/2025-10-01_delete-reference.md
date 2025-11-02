# Delete Related Paper Regression

## Purpose
Ensure deleting a related paper no longer triggers a 500 response that blocks CORS and leaves the entry undeleted.

## Setup
1. Backend and frontend containers rebuilt with the latest code: `docker compose up -d --build backend frontend`.
2. Frontend dev server accessible at http://localhost:3000 with an authenticated user who has an active project containing at least one related paper.
3. Browser dev tools network tab open to monitor the DELETE request.

## Test Data
Use any project where a related paper is attached. No special fixtures required.

## Steps
1. Navigate to the project's Related Papers tab.
2. Identify a related paper and click the delete (remove) action.
3. Observe the DELETE request in the network tab.
4. Refresh the list of related papers.

## Expected Results
- The DELETE request returns HTTP 204 with CORS headers.
- No 500 errors appear in `docker compose logs backend`.
- The related paper entry is removed from the list after the refresh.

## Rollback
If the request still fails, revert to the previous backend image (`docker compose rollback backend` if available) or reapply the prior code and rebuild. Reattach the related paper if it was removed during testing.

## Evidence
Backend log excerpt showing successful 204 response (capture via `docker compose logs backend --tail=20`).
