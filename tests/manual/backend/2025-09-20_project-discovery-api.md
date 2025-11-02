# Project Discovery API

## Purpose
Validate project discovery settings CRUD and manual discovery run endpoints.

## Setup
- Backend virtualenv `scholarenv` activated.
- Postgres running with latest migration (`a94f5b285ae3`).
- Feature flag `PROJECT_REFERENCE_SUGGESTIONS_ENABLED=true`.
- Auth token for `g202403940@kfupm.edu.sa`.

## Steps
1. `GET /api/v1/projects/<project_id>/discovery/settings` returns defaults (empty query, auto off).
2. `PUT /api/v1/projects/<project_id>/discovery/settings` with new query/keywords responds 200 and values persist on subsequent GET.
3. `POST /api/v1/projects/<project_id>/discovery/run` returns counts and updates `last_run_at` in settings.
4. `POST /api/v1/projects/<project_id>/references/suggestions/refresh` auto-triggers discovery when `auto_refresh_enabled` is true.

## Expected Results
- Settings updates require owner/editor rights and persist to `projects.discovery_preferences`.
- Manual run queues new `project_references` (pending) when discovery locates unseen papers.
- Refresh endpoint includes `discovery` summary when auto mode is active.

## Rollback
Reapply settings with blank fields or disable auto refresh.

## Evidence
- Verified via curl/Postman; no screenshots captured.
