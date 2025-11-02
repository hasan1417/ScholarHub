# Channel Chat Visibility

**Purpose**
- Verify that newly sent discussion messages display immediately within the active channel without needing a manual refresh.

**Setup**
- Docker stack running with frontend and backend services (`docker compose up -d backend frontend`).
- Test user account with membership in a project that has at least one discussion channel.
- Browser session authenticated as that user.

**Test Data**
- Project: any project with an existing discussion channel (e.g., "Agentic AI Study").
- Message payloads:
  - New root message: "Channel visibility smoke test".
  - Reply message: "Follow-up reply visibility test".

**Steps**
1. Sign in to ScholarHub and navigate to the chosen project.
2. Open the **Discussion** tab and select a non-archived channel from the sidebar.
3. Enter the root test message in the composer and press **Enter** to send.
4. Confirm the message renders immediately in the conversation list without reloading the page.
5. Reply to the newly created thread with the reply test message.
6. Observe that the reply appears under the thread and the reply counter increments.
7. Refresh the page to ensure both messages persist after a full reload.

**Expected Results**
- The root message renders instantly at the bottom of the conversation timeline.
- The sender sees their own message row with the tinted indigo background used in AI chat, while other users’ messages stay neutral.
- The reply displays under the parent thread in chronological order, and the parent reply count increments by one.
- After a full page reload, both messages remain visible in the same channel.

**Rollback**
- Delete the test thread (root message) via the message actions menu to keep the discussion clean.

**Evidence**
- Not captured (local verification only).
