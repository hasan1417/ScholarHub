# Manual Test - Daily Call Token Flow

## Purpose
Validate that Sync Space issues Daily meeting tokens, protects direct joins without a valid token, and expires access once the session ends.

## Setup
- Backend running locally with `.env` configured for `PROJECT_MEETINGS_ENABLED`, `DAILY_API_KEY`, `DAILY_DOMAIN`, and `SYNC_CALLBACK_TOKEN`.
- Frontend dev server running via `npm run dev`.
- Authenticated editor/admin user with an existing project.
- Optional: browser DevTools open on the Network tab to inspect token responses.

## Test Data
- Project: any project where you have editor rights.
- Daily domain: `https://scholarhub.daily.co` (configured in `.env`).

## Steps
1. Open the project and navigate to **Sync Space**.
2. Click **Start session** and wait for the live session card to appear.
3. Click **Open call window**. Observe that a new tab opens to `https://scholarhub.daily.co/<room>?t=<token>`.
4. In DevTools → Network, inspect `POST /api/v1/projects/<project>/sync-sessions/<session>/token`; confirm the JSON payload includes `provider: "daily"`, a `join_url`, and `domain`.
5. Copy the Daily join URL, remove the `?t=<token>` suffix, and attempt to load it in an incognito/private window. Verify Daily rejects the request.
6. Return to Sync Space and click **End session**. Allow the UI to refresh and move the session to the Past list.
7. Attempt to reuse the earlier `?t=<token>` link. Daily should return an access error because the token has expired.

## Expected Results
- Step 3: Call window loads Daily Prebuilt UI using the configured domain and token.
- Step 4: Token response exposes Daily metadata (`provider`, `room_url`, `join_url`) and `join_url` contains `?t=`.
- Step 5: Direct access without the token results in an authorization error from Daily.
- Step 7: Ended session invalidates the token; the join link no longer opens the room.

## Rollback
- None required. Tokens expire automatically and the finished session stays archived.

## Evidence
- Screenshot or HAR showing the `POST /token` response with `provider: "daily"`.
- Browser message from Daily refusing the tokenless join attempt.
