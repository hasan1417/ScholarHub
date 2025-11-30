Purpose:
- Verify the paper AI chat can see the current draft excerpt and respond using both the draft and processed references.

Setup:
- Backend and frontend running.
- A paper with some draft text in the editor and at least one analyzed reference (PDF processed).

Test Data:
- Draft text containing a unique phrase (e.g., “quantum flux draft note”).

Steps:
1) Open the paper editor and ensure the draft contains the unique phrase; open AI Chat.
2) Ask “What is in my draft right now?” and wait for the streamed reply.
3) Ask a reference question (e.g., “Summarize the main contribution”) and confirm references are still used.

Expected Results:
- Step 2: Reply reflects the draft excerpt (mentions the unique phrase) without claiming it cannot see the draft.
- Step 3: Reply remains concise, grounded in references; if multiple references are used, brief source tags appear.

Rollback:
- None required.

Evidence:
- Screenshot of the chat showing the draft-aware reply (`tests/manual/_evidence/2025-11-26_reference-chat-draft-context.png`).
