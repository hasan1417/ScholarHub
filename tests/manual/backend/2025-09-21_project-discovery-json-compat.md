# Project Discovery JSON Snapshot Compatibility

## Purpose
Ensure manual discovery runs persist without JSON serialization errors when preferences include timestamps.

## Setup
- Backend virtualenv `scholarenv` activated with dependencies installed.
- Postgres service running with migrations applied.
- Feature flags enabling discovery (`PROJECT_REFERENCE_SUGGESTIONS_ENABLED=true`).
- Project seeded with discovery preferences containing `last_run_at` (trigger at least one prior run before testing) and auth token for an editor/owner.

## Steps
1. Issue `POST /api/v1/projects/<project_id>/discovery/run` with body `{}` using the prepared auth token.
2. Monitor backend logs for insert statements touching `project_discovery_runs`.
3. Query `project_discovery_runs` for the project to confirm the new row was created.
4. Fetch `GET /api/v1/projects/<project_id>/discovery/settings` and verify `last_run_at` remains an ISO8601 string.

## Expected Results
- Step 1 responds 200 with run counts and no 500 error.
- Backend logs show successful insert without `datetime is not JSON serializable` errors.
- Step 3 reveals the new run row with a populated `settings_snapshot` JSON payload.
- Step 4 returns settings with `last_run_at` formatted as an ISO timestamp string.
- If the discovery tables are absent, endpoints respond 503 instructing operators to run the latest migrations instead of throwing tracebacks.

## Rollback
No data changes needed; leave discovery settings as-is or reset via the settings endpoint if desired.

## Evidence
- Verified via backend logs and direct Postgres query; no screenshots captured.
