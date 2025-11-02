# Daily Stack for Sync Space

Sync Space now uses [Daily](https://www.daily.co/) for real-time audio rooms, so there is no longer a need to run a self-hosted Jitsi cluster. This document captures the minimum setup required to issue Daily meeting tokens from the backend and to ingest recordings back into ScholarHub.

## Prerequisites

- A Daily account with API access enabled. Create one at <https://dashboard.daily.co/>.
- A domain or subdomain provisioned by Daily (e.g. `scholarhub.daily.co`).
- Daily REST API key (Dashboard → Developers → API keys).
- Optional: a server that will post meeting recordings back to ScholarHub (Daily’s cloud recording webhooks, or your own recorder pipeline).

## Configuration Summary

| Setting | Where | Purpose |
| --- | --- | --- |
| `DAILY_API_KEY` | `backend/.env` | Authenticates backend requests to the Daily REST API. |
| `DAILY_DOMAIN` or `DAILY_ROOM_BASE_URL` | `backend/.env` | Base URL used to build room links (`https://<domain>/<room>`). If you have a custom domain, use `DAILY_ROOM_BASE_URL`; otherwise set `DAILY_DOMAIN` to the Daily-provided subdomain. |
| `DAILY_API_BASE_URL` (optional) | `backend/.env` | Override when using Daily’s EU region (`https://api.eu.daily.co/v1`). |
| `DAILY_ROOM_TTL_SECONDS` (optional) | `backend/.env` | Expiry (in seconds) applied when rooms are auto-created. Defaults to 6 hours. |
| `DAILY_TOKEN_TTL_SECONDS` (optional) | `backend/.env` | Time-to-live for meeting tokens. Defaults to 1 hour. |
| `SYNC_CALLBACK_TOKEN` | `backend/.env` | Shared secret expected on recording webhooks (`X-Sync-Token` header). |
| `DAILY_WEBHOOK_SECRET` | `backend/.env` | Secret used to verify Daily webhook signatures (`X-Daily-Signature`). |
| `DAILY_WEBHOOK_URL` (optional) | `backend/.env` | Override the webhook callback URL; defaults to `<BACKEND_PUBLIC_URL>/api/v1/integrations/daily/webhook`. |
| `DAILY_ENABLE_RECORDING` (optional) | `backend/.env` | Set to `cloud` (default) for composite recording, or `raw-tracks` when you need per-participant tracks. |
| `DAILY_RAW_TRACKS_S3_BUCKET` / `REGION` / `ACCESS_KEY_ID` / `SECRET_ACCESS_KEY` / `PREFIX` | `backend/.env` | Optional when `DAILY_ENABLE_RECORDING=raw-tracks`; fills Daily’s S3 upload settings so audio archives land in your bucket. |
| `DAILY_START_CLOUD_RECORDING` (optional) | `backend/.env` | When `true`, Daily rooms automatically start recording as soon as a participant joins. |
| `DAILY_RECORDING_AUDIO_ONLY` (optional) | `backend/.env` | When `true` and using `cloud`, Daily records audio-only. Ignored for `raw-tracks`. |
| `PROJECT_MEETINGS_ENABLED=true` | `backend/.env` | Enables the Sync Space feature flag. |
| `VITE_API_BASE_URL` | `frontend/.env` | Already required; ensure it points at the backend so tokens can be fetched. |

### Example backend `.env`

```env
PROJECT_MEETINGS_ENABLED=true
DAILY_API_KEY=sk_live_your_daily_key
DAILY_DOMAIN=scholarhub.daily.co
# Alternate form if you front Daily with your own host
# DAILY_ROOM_BASE_URL=https://meet.scholarhub.dev
DAILY_ROOM_TTL_SECONDS=21600
DAILY_TOKEN_TTL_SECONDS=3600
SYNC_CALLBACK_TOKEN=change-me
DAILY_WEBHOOK_SECRET=change-me
DAILY_WEBHOOK_URL=https://your-backend.example/api/v1/integrations/daily/webhook
DAILY_ENABLE_RECORDING=raw-tracks
DAILY_START_CLOUD_RECORDING=true
DAILY_RECORDING_AUDIO_ONLY=false
DAILY_RAW_TRACKS_S3_BUCKET=your-s3-bucket
DAILY_RAW_TRACKS_S3_REGION=us-east-1
DAILY_RAW_TRACKS_S3_ACCESS_KEY_ID=your-access-key
DAILY_RAW_TRACKS_S3_SECRET_ACCESS_KEY=your-secret-key
DAILY_RAW_TRACKS_S3_PREFIX=recordings/
BACKEND_PUBLIC_URL=http://localhost:8000
```

Restart the backend after updating the environment variables. No Docker services are required for Daily—only the standard ScholarHub backend and frontend.

## Call Flow

1. From the Sync Space tab, press **Start session**. The backend now creates (or reuses) a Daily room using the prefix defined by `SYNC_ROOM_PREFIX` (defaults to `sync`).
2. When a user clicks **Open call window**, the frontend calls `POST /api/v1/projects/{projectId}/sync-sessions/{sessionId}/token`.
3. The backend mints a Daily meeting token via `POST /meeting-tokens`, returning a `join_url` in the response. The browser opens that link in a new tab.
4. Once the session ends, `POST /sync-sessions/{id}/end` revokes the ability to mint new tokens, blocking re-entry to the room.

New rooms are provisioned with `enable_recording=cloud`, and when `DAILY_START_CLOUD_RECORDING=true`, Daily auto-starts cloud recording as soon as someone joins.

### Managing History

Use the **Clear ended sessions** button in Sync Space to remove archived cards once you no longer need them. The backend erases ended/cancelled sessions (and associated recordings) while keeping active sessions untouched.

When the webhook supplies an `audio_url`, the session card exposes an **Open call recording** link. In raw-tracks mode (with S3 credentials configured) this downloads a `.zip` with per-participant audio files; extract the archive to listen back or feed it into downstream tooling.

### Recording Webhook

1. Set `DAILY_WEBHOOK_SECRET` in `backend/.env` (and optionally override `DAILY_WEBHOOK_URL`).
2. If `BACKEND_PUBLIC_URL` is configured, the backend automatically registers a Daily webhook pointing at `<BACKEND_PUBLIC_URL>/api/v1/integrations/daily/webhook` for the `participant.joined` and `recording.ready-to-download` events (falling back to `recording.ready` on older accounts). The URL must be publicly reachable by Daily (no `localhost`/Docker-only hosts) or registration is skipped.
3. Daily signatures are validated using `DAILY_WEBHOOK_SECRET`. When `participant.joined` fires, ScholarHub retries the recording start; when `recording.ready-to-download` fires (or the legacy `recording.ready`), the `download_link` is attached to the session card.
4. Optional: keep `SYNC_CALLBACK_TOKEN` if you still run custom upload scripts—the legacy endpoints continue to work.

Daily rooms are deleted automatically once a Sync Space session is ended so the Daily dashboard stays tidy.

## Recording Webhooks

If you capture audio/video on the server side (Daily’s [cloud recordings](https://docs.daily.co/reference/rest-api/recordings) or your own pipeline), call back into the backend once a file is ready:

1. Set `SYNC_CALLBACK_TOKEN` in `backend/.env` and reuse the same value in your recording service.
2. When a recording for room `sync-…` finishes, resolve the session:

   ```bash
   curl -H "X-Sync-Token: $SYNC_CALLBACK_TOKEN" \
        http://localhost:8000/api/v1/sync-sessions/by-room/sync-abcdef-1234567890
   ```

3. Upload metadata via `POST /projects/{projectId}/sync-sessions/{sessionId}/recording/callback` (the legacy `/recording/jibri` path continues to work for older scripts):

   ```bash
   curl -H "X-Sync-Token: $SYNC_CALLBACK_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{
              "audio_url": "https://your-storage/calls/abc123.mp3",
              "summary": "Optional precomputed summary",
              "transcript": {"segments": []}
            }' \
        http://localhost:8000/api/v1/projects/<projectId>/sync-sessions/<sessionId>/recording/callback
   ```

4. Alternatively, upload the file directly with multipart form data using `POST /projects/{projectId}/sync-sessions/{sessionId}/recording/callback/upload`.

The callback endpoints now expect `X-Sync-Token` but still respond on the previous paths so existing scripts remain compatible.

## Cleanup

Because Daily is fully managed, there are no additional containers to stop. Disabling the feature is as simple as setting `PROJECT_MEETINGS_ENABLED=false` or removing the Daily API key.
