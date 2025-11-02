# Channel AI History Persistence

**Purpose**
- Ensure Scholar AI exchanges within a discussion channel persist across page reloads.

**Setup**
- Docker stack running with frontend and backend services (`docker compose up -d backend frontend`).
- Project membership that can access the Discussion tab and invoke Scholar AI.
- Browser session authenticated as that member.

**Test Data**
- Project: any project with an active discussion channel (e.g., "Agentic AI Study").
- Prompt: `/reason Summarize our latest findings on dataset drift.`

**Steps**
1. Sign in and navigate to the target project’s Discussion tab.
2. Select a non-archived discussion channel.
3. In the composer, type the slash command prompt above and press **Enter** to submit it to Scholar AI.
4. Wait for the AI response to complete and verify it appears in the conversation timeline.
5. Refresh the page (Cmd/Ctrl+R) once the response finishes streaming.
6. After the reload completes, confirm the same AI prompt and response remain visible in the channel history.

**Expected Results**
- The prompt and AI reply appear back-to-back as regular discussion bubbles (author bubble tinted if it’s your account) with a small "AI prompt" badge beside the prompt metadata.
- The Scholar AI bubble shows the reply along with model/tokens metadata and any reasoning or suggested-action badges.
- After the page reload, both the prompt and the AI reply remain visible in the channel history for every member.

**Rollback**
- None required; AI prompts can remain for reference.

**Evidence**
- Not captured (local verification only).
