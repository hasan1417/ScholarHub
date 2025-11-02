# Manual Test - Daily API Connectivity

## Purpose
Verify Daily credentials provisioned for Sync Space can authenticate against the Daily REST API and manage rooms without relying on the legacy Jitsi stack.

## Setup
- Backend `.env` populated with `DAILY_API_KEY` and `DAILY_DOMAIN`.
- Shell with `curl` or HTTP client capable of setting custom headers.
- Optional: `jq` installed for prettier JSON output.

## Test Data
- Room slug to create (if missing): `sync-space-manual-test`.

## Steps
1. Export the API key locally: `export DAILY_API_KEY="$(grep DAILY_API_KEY .env | cut -d= -f2-)"`.
2. List existing rooms: `curl -H "Authorization: Bearer $DAILY_API_KEY" https://api.daily.co/v1/rooms | jq '.rooms | length'`.
3. Ensure the Sync Space prefix room exists: `curl -H "Authorization: Bearer $DAILY_API_KEY" -H "Content-Type: application/json" \
   -d '{"name":"sync-space-manual-test","privacy":"private"}' \
   -X POST https://api.daily.co/v1/rooms` (expect HTTP 200 or 409 if already present).
4. Request a meeting token to confirm join permissions: `curl -H "Authorization: Bearer $DAILY_API_KEY" -H "Content-Type: application/json" \
   -d '{"properties":{"room_name":"sync-space-manual-test","is_owner":true,"user_id":"manual-test"}}' \
   -X POST https://api.daily.co/v1/meeting-tokens`.
5. Open `https://scholarhub.daily.co/sync-space-manual-test?t=<token>` in a browser using the token from the previous step and confirm the Daily lobby loads.

## Expected Results
- Step 2: API responds with HTTP 200 and returns a list of rooms (possibly empty).
- Step 3: Creating the room succeeds (HTTP 200) or returns 409 indicating it already exists.
- Step 4: Meeting token endpoint responds with HTTP 200 and a `token` string.
- Step 5: Daily lobby renders using the configured `scholarhub.daily.co` domain.

## Rollback
- Delete the manual room if desired: `curl -H "Authorization: Bearer $DAILY_API_KEY" -X DELETE https://api.daily.co/v1/rooms/sync-space-manual-test`.

## Evidence
- Save the JSON responses (room list and meeting token) or screenshots of the Daily lobby using the generated token.
