# Manual Test - Sync Space Session API Surface

**Purpose**
Validate that the Sync Space tab fetches session data from the backend, spins up a Daily-backed call, and renders the token/join workflow alongside chat history actions.

**Setup**
1. Backend running locally with migrations applied (`alembic upgrade head`).
2. Frontend dev server running (`npm run dev`).
3. Authenticated user with editor/admin access to a project.
4. `.env` populated with `PROJECT_MEETINGS_ENABLED=true`, `DAILY_API_KEY`, and `DAILY_DOMAIN=scholarhub.daily.co`.

**Steps**
1. Open the project workspace and click the **Sync Space** tab.
2. Watch the network panel for `GET /api/v1/projects/<projectId>/sync-sessions`; confirm it resolves with HTTP 200.
3. Click **Start session**.
4. Confirm the button shows the loading state, the POST `/sync-sessions` request returns HTTP 201, and the sessions list refreshes with a Live card exposing the provider details.
5. Click **Open call window** on the live card; confirm `POST /sync-sessions/<id>/token` returns HTTP 200 and the browser opens `https://scholarhub.daily.co/<room>?t=<token>` in a new tab.
6. Observe the live card updates with the Daily domain/link.
7. Click the Live session card’s **Open chat** action; verify a new window opens to the same Sync Space route with `session` and `view=chat` query params populated.
8. Click **End session**, confirm `POST /sync-sessions/<id>/end` returns HTTP 200 and the session moves to the Past list with transcript placeholders.
9. Reload the page and verify the session stays under past syncs with status `ended` and no longer surfaces a live call link.

**Expected Results**
- Step 2: The sessions request succeeds and the UI shows loading shimmer while awaiting data.
- Step 3-4: Starting a call triggers the POST endpoint and the list updates without manual reload, showing the Daily provider metadata.
- Step 5: Fetching a token returns `join_url` and the opened tab renders the Daily Prebuilt UI.
- Step 6: Live card surfaces the Daily domain and room link.
- Step 7: “Open chat” spawns a new window including both session and view query parameters.
- Step 8: Ending the session completes successfully and removes it from the Active list.
- Step 9: After refresh, the session is listed under past syncs without an active call link.

**Rollback**
- Optionally delete the session via database if cleaning up test data.

**Evidence**
- HAR or screenshots showing the GET/POST responses and refreshed UI state.
