# Purpose
Verify the bottom-center AI Chat trigger opens a context-aware chat that uses the current draft text and attached references.

# Setup
- Backend and frontend running (docker compose stack).
- Logged-in user with access to a paper that has draft content; references attached to the paper (if available).
- LaTeX editor reachable (e.g., open a paper from Projects → Paper → Edit).

# Test Data
- An existing paper with draft text. Optional: at least one attached reference to see reference context.

# Steps
1. Open the paper in the LaTeX editor; confirm the bottom-center “AI CHAT” pill is visible.
2. Click the pill; the AI Chat panel should appear above the bottom edge.
3. If any attached references lack PDFs, observe the amber notice prompting to attach PDFs.
4. Enter a question (e.g., “Summarize the findings in this draft”) and press Enter; wait for the assistant reply.
5. While the reply is generating, a typing indicator (bouncing dots) appears under “Assistant”; when done, the reply appears and the history shows “You” then “Assistant.” The send button disables while loading.
6. Close the panel with the X and reopen it; history should reset and the pill remains at bottom-center.

# Expected Results
- The AI Chat panel opens from the bottom-center trigger; close works.
- Missing-PDF notice appears when applicable.
- Sending a question results in an assistant response; errors are surfaced inline if the call fails.
- While sending, the button shows a spinner and prevents duplicate submissions; a typing indicator is visible until the assistant reply arrives.
- If no processed references exist, the chat responds with a warning that PDFs are missing (listing the titles) instead of failing outright.

# Rollback
- None; UI-only change.

# Evidence
- Screenshots of the open chat panel showing context and a successful response under `tests/manual/_evidence/2025-11-23_ai-chat-button/`.
