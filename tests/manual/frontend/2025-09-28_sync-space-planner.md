# Manual Test - Sync Space Session Planner

**Purpose**
Validate that the Session Planner modal opens from a sync session, exposes quick commands, lets the user run a manual GPT-5 prompt, and surfaces the meeting transcript alongside generated outputs.

**Setup**
1. Backend services running with Daily integration and transcript pipeline (`uvicorn app.main:app --reload`).
2. Frontend dev server running (`npm run dev`) with an authenticated project member (editor or admin).
3. Target project contains at least one sync session with a completed transcript.

**Steps**
1. Visit `http://localhost:3000/projects/<projectId>/sync-space`.
2. Pick an ended session card and click `Open planner`.
3. Verify the modal header shows “Session Planner”, the status pill (Ready/Running/Retry needed), and the “Powered by GPT-5…” helper copy.
4. Under **Quick actions**, run `Summarize meeting`; confirm the button disables and the **Latest insight** card refreshes with the new response.
5. In **Manual prompt**, enter a custom instruction (e.g., “Draft a follow-up email highlighting key decisions”).
6. Press `Enter` to submit; use `Shift+Enter` to insert a newline and ensure it does not send.
7. Confirm the manual prompt updates **Latest insight** and shifts the previous summary into **Earlier runs**.
8. Scroll the **Call transcript** panel to confirm the transcript text is available (or the placeholder message if not yet processed).
9. Close the planner via `X`, reopen it, and ensure the output history persists during the session.
10. Navigate to the **Updates** tab and confirm a "Session planner run" event is logged with your prompt preview.

**Expected Results**
- Step 3: Modal uses neutral styling with only the status pill and start time; no chat thread appears.
- Step 4: Quick action sends the canned prompt, displays a spinner, then shows the generated summary inside **Latest insight**.
- Step 6: `Enter` submits immediately; `Shift+Enter` adds a newline without sending.
- Step 7: Manual prompt response becomes the top card in **Latest insight**, with the prior run archived under **Earlier runs**.
- Step 8: Transcript panel shows meeting text or a clear placeholder when absent.
- Step 9: Planner retains prior outputs while open; no console errors occur.
- Step 10: Updates feed lists the new session planner entry with prompt and output previews.

**Rollback**
None required.

**Evidence**
- Capture: `tests/manual/_evidence/2025-09-28_session-planner.png` (planner modal showing quick actions, manual prompt, recent outputs, and transcript).
