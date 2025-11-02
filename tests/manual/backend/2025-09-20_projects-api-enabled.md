# Projects API Feature Flags Enabled

## Purpose
Ensure the backend exposes project endpoints when the project-first migration flags are enabled so the Projects home no longer hits 404.

## Setup
- Backend virtualenv `scholarenv` activated.
- `.env` updated with `PROJECTS_API_ENABLED=true` and related flags.
- Database seeded with at least one user (`g202403940@kfupm.edu.sa`).

## Test Data
- Credentials: `g202403940@kfupm.edu.sa` / `testpass123`.

## Steps
1. Restart the FastAPI server so it reloads the updated `.env`.
2. Send `POST /api/v1/login` with the test credentials and capture the `access_token`.
3. Call `GET /api/v1/projects` with the `Authorization: Bearer <token>` header.

## Expected Results
- Login returns HTTP 200 with a bearer token.
- Projects request returns HTTP 200 with a `projects` array (empty if no projects yet) rather than 404.

## Rollback
Revert feature flags in `backend/.env` if you need to restore the legacy dashboard flow.

## Evidence
- Verified route registration via Quick `TestClient` script listing `/api/v1/projects` paths.
