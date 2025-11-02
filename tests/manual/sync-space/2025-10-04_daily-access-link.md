# Daily Recording Access-Link Transcription

## Purpose
Validate that Daily recordings without an inline `download_link` are transcribed successfully via the new access-link fallback and deleted after transcription.

## Setup
- Running docker compose stack: `postgres`, `redis`, `backend`, `transcriber`.
- `.env` contains valid `OPENAI_API_KEY`, `DAILY_API_KEY`, and `USE_OPENAI_TRANSCRIBE=true`.
- Docker backend image rebuilt with latest code (`docker compose up -d --build backend`).

## Test Data
- Project ID: `7ce05847-1dc3-4ebb-b930-0b093ee63f3e`
- Sync session ID: `1273f27e-6af7-46f3-b4b9-14237a94e5f6`
- Meeting placeholder ID: `eec9b9d0-3dfe-465a-ac95-9995c755d5a5`
- Daily recording ID: `8fe67fe1-496f-49b6-8cfc-dc04fd5274a9`

## Steps
1. End the Daily room from the UI so a recording is generated (meeting status shows "Transcription in progress").
2. Wait for the backend worker to pick up the recording (or run `_poll_daily_recording` from a backend shell to trigger immediately).
3. After the background task finishes, query Postgres for the meeting row and associated sync session payload (see Evidence file for exact SQL).

## Expected Results
- Meeting moves from `transcribing` to `completed` with `transcript.provider=openai` and populated `transcript.text`.
- `project_sync_sessions.provider_payload` contains `recording_ready_at` followed by `recording_deleted_at`, with no lingering `recording_id` or `recording_url`.
- No backend errors about missing Daily download links or failed deletion (warnings only if the recording is already gone).

## Rollback
Remove or archive the generated meeting transcript if needed: `UPDATE meetings SET transcript = '{}' WHERE id = 'eec9b9d0-3dfe-465a-ac95-9995c755d5a5';`

## Evidence
- `tests/manual/_evidence/2025-10-04_daily-access-link.txt`
