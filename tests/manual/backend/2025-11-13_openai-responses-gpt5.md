# Purpose
Validate that backend services now use the OpenAI Responses API with the `gpt-5` model family, covering discussion streaming and shared AI utility endpoints.

# Setup
1. Pull latest code and run `pip install -r backend/requirements.txt` inside `backend/scholarenv` to install `openai==2.8.1`.
2. Export a valid `OPENAI_API_KEY` that has access to `gpt-5` plus the existing `gpt-4o-mini` tier.
3. Start postgres/redis via `docker compose up -d postgres redis` and run the backend (`uvicorn app.main:app --reload`).
4. Run the frontend dev server (`npm run dev`) and sign in as a project member with at least one populated discussion channel and paper.

# Test Data
- Existing project with an active discussion channel.
- Sample question to ask the assistant, e.g., “Summarize the latest objectives in this project.”

# Steps
1. In the frontend discussion UI, select the project channel and submit the sample question.
2. Observe the streaming tokens; confirm the assistant replies without 400 errors in the console/network tab.
3. Inspect backend logs for the request and verify the `model` logged for `DiscussionAIService` shows `gpt-5`.
4. Hit the `/api/v1/ai/text-tools` endpoint from the UI (Profile → Text Tools) with a short paragraph; ensure the response arrives and no “unsupported parameter” errors appear in logs.
5. (Optional) Trigger a literature review generation to ensure the long-form helpers still return content.

# Expected Results
- Discussion responses stream token-by-token without disconnects; the final reply includes citations as before.
- Backend logs confirm the Responses API path is used (no `chat.completions` warnings) and the `Usage` metadata lists `input_tokens`/`output_tokens`.
- Text tools requests succeed using `gpt-4o-mini` via `/responses`; no 400 errors referencing `max_tokens`.
- Optional literature review completes and produces sections without runtime errors.

# Rollback
- Shut down the dev servers (`Ctrl+C`) and `docker compose down` the shared services once validation finishes.

# Evidence
- Capture a short screen recording or screenshot of the streaming discussion reply and attach to `tests/manual/_evidence/2025-11-13_openai-responses-gpt5.mp4` if needed.
