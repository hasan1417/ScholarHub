# Purpose
Demonstrate that the self-hosted faster-whisper service accepts audio uploads through the backend proxy endpoint and returns a transcript.

# Setup
- Start the transcription container alongside the backend: `docker compose up -d transcriber backend`.
- Ensure the backend `.env` includes `TRANSCRIBER_ENABLED=true` and (optionally) `TRANSCRIBER_BASE_URL=http://transcriber:9000` for in-cluster access.
- Restart the backend so the new settings are applied.

# Test Data
Short audio clip (≤15 seconds) saved as `tests/manual/_evidence/resources/hello.wav` stating “Hello ScholarHub this is a transcription test”.

# Steps
1. Log in to the ScholarHub API (or reuse an existing token).
2. Send `POST http://localhost:8000/api/v1/transcription` with multipart form data: field `file=@hello.wav`.
3. Observe the JSON response.

# Expected Results
- HTTP 200 response containing `transcript` with the spoken sentence (allowing minor punctuation differences).
- `metadata.model` matches the configured model size (default `tiny`).
- `metadata.processing_seconds` is non-zero and reasonably small (<30s for the sample).

# Rollback
- Disable the feature flag (`TRANSCRIBER_ENABLED=false`) and restart the backend if the endpoint should be hidden.
- Stop the transcriber container when not in use: `docker compose stop transcriber`.

# Evidence
- Capture the HTTP response (CLI output or screenshot) and store under `tests/manual/_evidence/2025-09-25_transcriber.png`.
