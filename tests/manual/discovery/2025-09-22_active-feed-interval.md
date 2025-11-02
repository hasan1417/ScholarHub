# Project Discovery Auto Refresh Interval

## Purpose
Verify that the Project Discovery auto-refresh interval can be configured to five minutes and that background runs respect the shorter cadence.

## Setup
- ScholarHub stack running (frontend + backend) with valid credentials for a project editor.
- Feature flag `PROJECT_REFERENCE_SUGGESTIONS_ENABLED=true`.
- Project with at least one prior discovery run so preferences exist.
- Admin access to database or API tooling to inspect `project_discovery_runs`.

## Test Data
- Target project ID and authentication token for an editor or admin member.
- Optional: existing discovery preferences to observe before/after values.

## Steps
1. Navigate to the project and open the **Discovery** tab (editor or admin role).
2. Enable **Enable active search feed (auto-refresh)** and set **Refresh interval (minutes)** to `5`.
3. Click **Save preferences** and confirm the request succeeds (status 200 in browser network tools).
4. Inspect `GET /api/v1/projects/<project_id>/discovery/settings` and confirm `auto_refresh_enabled` is `true` and `refresh_interval_hours` is approximately `0.0833`.
5. Keep the Discovery page open; the UI will automatically invoke `POST /api/v1/projects/<project_id>/references/suggestions/refresh` once the five-minute interval elapses (or call it manually if you need to force a run).
6. Query `project_discovery_runs` (or call `GET /api/v1/projects/<project_id>/discovery/results?status=pending`) and verify a new run record exists with `run_type = 'auto'` and `started_at` within the last ~5 minutes.
7. View the **Active search feed** tab and confirm new pending suggestions appear (or the empty-state indicates the background run completed with no new items).

## Expected Results
- Preferences endpoint reflects the five-minute interval in hours (`0.0833`).
- Background refresh completes without HTTP 500 or validation errors.
- Auto discovery run rows show `run_type = 'auto'` with the updated `settings_snapshot` containing the new interval.
- Active feed displays the five-minute cadence chip (e.g., “Auto-refresh every 5 min”) and surfaces newly discovered results when available.

## Rollback
- Optionally reset the interval to the previous value (e.g., 1440 minutes for daily) or disable auto-refresh via the toggle.

## Evidence
- Screenshot or log excerpt showing the updated discovery settings response and the corresponding `project_discovery_runs` entry.
