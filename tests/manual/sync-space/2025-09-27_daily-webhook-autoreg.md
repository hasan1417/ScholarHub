# Daily Webhook Auto-Registration

- **Purpose**: Verify the backend can register the Daily webhook even when the API expects different `event*_` field names.
- **Setup**:
  - Backend running with `PROJECT_MEETINGS_ENABLED=true`, `DAILY_API_KEY`, `DAILY_DOMAIN`, `DAILY_WEBHOOK_SECRET`, and `BACKEND_PUBLIC_URL=http://localhost:8000` in `backend/.env`.
  - Ensure the backend has been restarted after updating the environment variables.
  - Daily API key exported locally as `DAILY_API_KEY` for CLI checks.
- **Test Data**: Project `ScholarHub Sync QA` (`7ce05847-1dc3-4ebb-b930-0b093ee63f3e`).
- **Steps**:
  1. Tail backend logs with `tail -f uvicorn.log` and trigger a Sync Space load (e.g., `GET /api/v1/projects/.../sync-sessions`) to instantiate `VideoService`.
  2. Observe the log line `Registered Daily webhook` (or `Skipping Daily webhook setup` when already present).
  3. Run `curl -H "Authorization: Bearer $DAILY_API_KEY" https://api.daily.co/v1/webhooks` and confirm at least one record matches `url: http://localhost:8000/api/v1/integrations/daily/webhook` with events that include `participant.joined` and `recording.ready-to-download` (legacy accounts may still show `recording.ready`).
  4. If a webhook already exists, delete it from the Daily dashboard, repeat Step 1, and verify the backend re-registers it without a 400 error.
- **Expected Results**:
  - Backend logs show a single registration attempt without 400 responses for unsupported `event` field names.
  - Daily API lists the webhook with both `participant.joined` and `recording.ready-to-download` (or the legacy `recording.ready`) events.
  - When the callback URL is not publicly reachable (e.g., `localhost`), the backend logs `Daily webhook endpoint is unreachable from Daily's network; skipping auto-registration` and stops retrying.
  - Repeating the request after manual deletion succeeds on the first attempt.
  - Note: For `raw-tracks`, set the `DAILY_RAW_TRACKS_S3_*` env vars so Daily can upload archives to your bucket.
- **Rollback**: Delete the verification webhook in the Daily dashboard if you do not want it to remain active.
- **Evidence**: [`tests/manual/_evidence/2025-09-27_daily-webhook.json`](../_evidence/2025-09-27_daily-webhook.json)
