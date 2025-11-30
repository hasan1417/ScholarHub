Purpose:
- Verify the paper AI chat routes context dynamically (draft vs references vs both) and avoids answering when no context is available.

Setup:
- Backend and frontend running.
- One paper with draft text (include a unique phrase) and at least one analyzed reference.

Steps:
1) Ask in paper chat: “What is in my draft right now?” — expect it to use the draft and ignore references unless asked.
2) Ask: “What references do I have?” — expect it to use references (titles/status) and not claim it cannot see the draft.
3) Ask: “Compare my draft to the references” — expect it to draw from both draft excerpt and reference chunks.
4) Temporarily remove draft text (empty) and ask “What is in my draft?” — expect a clear message that no draft text is available (not hallucinated reference content).

Expected Results:
- Step 1: Reply summarizes the draft excerpt (mentions the unique phrase); does not cite references.
- Step 2: Reply lists references and/or counts; no draft summary.
- Step 3: Reply references both sources succinctly.
- Step 4: Reply states no draft text is available.

Rollback:
- None needed; re-enter draft text if removed.

Evidence:
- Screenshot of the three replies showing correct routing (`tests/manual/_evidence/2025-11-26_context-router.png`).
