# Daily Call Integration Smoke Test

- **Purpose**: Verify that Sync Space sessions use Daily for call links and that tokens/join URLs are delivered correctly after the backend migration.
- **Setup**:
  - Backend running with `PROJECT_MEETINGS_ENABLED=true`, `DAILY_API_KEY`, `DAILY_DOMAIN=scholarhub.daily.co`, and `DAILY_WEBHOOK_SECRET` in `backend/.env`.
  - Frontend dev server running at `http://localhost:3000`.
  - Logged in as a project editor.
- **Test Data**: Existing project `ScholarHub Sync QA` (ID `7ce05847-1dc3-4ebb-b930-0b093ee63f3e`).
- **Steps**:
  1. Ensure Daily dashboard webhook is configured for `recording.ready-to-download` (or legacy `recording.ready`) pointing to `/api/v1/integrations/daily/webhook` with the shared secret.
  2. Navigate to `Projects → ScholarHub Sync QA → Sync Space`.
  3. Click **Start session** and wait for the live session card to appear.
  4. Click **Open call window**.
  5. Inspect the newly opened tab and verify the URL matches `https://scholarhub.daily.co/sync-…?t=<token>`.
  6. In DevTools → Network, confirm `POST /api/v1/projects/.../sync-sessions/.../token` returns `provider: "daily"` and a `join_url`.
  7. Return to the session card and confirm the call link shows the Daily URL.
  8. Click **End session**, wait for the card to move to Past Sessions, then attempt to re-open the earlier Daily URL (should fail because the token is single-use/expired).
  9. (Optional) Run `curl -H "Authorization: Bearer $DAILY_API_KEY" https://api.daily.co/v1/rooms/<room-name>` and confirm `properties.enable_recording` is `"cloud"` (and `start_cloud_recording` is `true` when enabled).
  10. If the Daily recording callback has populated an `audio_url`, click **Open call recording** to download the raw-tracks `.zip` and confirm the expected audio files are inside.
  11. (Optional) Click **Clear ended sessions** and confirm the card disappears from the list.
  12. In the Daily dashboard, verify the room no longer appears (rooms are deleted automatically when sessions end).
- **Expected Results**:
  - Token response includes `join_url` with `?t=` parameter, and the browser tab renders Daily Prebuilt UI.
  - Session card lists provider "daily" and shows the call link using the Daily domain.
  - After ending the session, the call URL is no longer displayed and the join attempt returns an authentication error from Daily.
  - When a recording is available, the **Open call recording** link opens the raw-tracks archive once the `recording.ready-to-download` (or legacy `recording.ready`) webhook fires.
  - Clearing ended sessions removes the card from the list (and it stays gone after refresh).
  - Ended sessions delete the backing Daily room so the Daily dashboard stays tidy.
- **Rollback**: Delete the test sync session from the project if not needed. No additional cleanup required.
- **Evidence**: [`tests/manual/_evidence/2025-09-26_daily-token.json`](../_evidence/2025-09-26_daily-token.json)
