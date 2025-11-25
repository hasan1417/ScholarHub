# Purpose
Verify the LaTeX editor AI writing tools use `gpt-5-mini` while chat/discussion AI stays on `gpt-4o-mini`.

# Setup
- Backend and frontend running (docker compose stack or local) with a valid `OPENAI_API_KEY`.
- User account with access to an existing paper and LaTeX editor.
- Backend logs visible (`docker compose logs -f backend`).

# Test Data
- A paper with LaTeX content that includes a short paragraph to feed into the AI Assistant.

# Steps
1. Call `GET /api/v1/ai/models` (DevTools or `curl`) and confirm `chat_model` shows `gpt-4o-mini` and `writing_model` shows `gpt-5-mini`.
2. Open the paper’s LaTeX editor, launch AI Assistant → choose an action (e.g., Expand), submit a paragraph, and verify the request succeeds; in backend logs, confirm the entry indicating the writing model `gpt-5-mini` is used.
3. Open the chat/discussion AI, send a prompt, and verify a normal response; re-check `GET /api/v1/ai/models` to confirm `chat_model` remains `gpt-4o-mini` (writing call did not change it).

# Expected Results
- Model configuration endpoint reports `chat_model: gpt-4o-mini` and `writing_model: gpt-5-mini`.
- LaTeX AI Assistant calls complete successfully and backend logs show `gpt-5-mini` being used for writing.
- Discussion/chat responses work as before and the model configuration still reports `gpt-4o-mini` for chat.

# Rollback
- No data changes; none needed. If issues appear, restart backend to reset transient state.

# Evidence
- Save screenshots of the LaTeX AI Assistant result and backend log line showing `gpt-5-mini` under `tests/manual/_evidence/2025-11-23_model-selection/`.
