# Manual Test - Project Updates Activity Feed

**Purpose**
Confirm the Updates tab reflects major API activity including call lifecycle events, paper edits, and project metadata changes.

**Setup**
1. Container stack running (`docker compose up -d backend frontend postgres redis`).
2. Authenticate as a project admin/editor via the frontend.
3. Target project has at least one sync session and paper associated with it.

**Steps**
1. Visit `http://localhost:3000/projects/<projectId>/sync-space` and start a new call. End the call after a few seconds.
2. Navigate to `Projects → Papers`, create a new paper under the same project (or edit an existing one’s title/abstract).
3. Open the project details sidebar and update a visible field (e.g., project scope or keywords).
4. Switch to the **Updates** tab.
5. Confirm the feed now lists (each card shows both relative and absolute timestamps in its header):
   - A “Call started” entry with provider, status badge, and timestamp.
   - A “Call ended” (or “Call cancelled”) entry for the same session showing duration.
   - A “Paper created” or “Paper updated” entry referencing the paper title and fields changed.
   - A “Reference linked” entry if you attached a related paper to the project paper.
6. From the **Discovery** tab run a manual search, use **Add to project** on a result, then click the new **Delete result** control for that manual entry; return to **Updates** to confirm a “Related paper deleted” card appears.
   - A “Project updated” entry summarising the fields you changed.

**Expected Results**
- Step 1: Two entries (start/end) appear with accurate timestamps and status pills.
- Step 2: Paper entry surfaces with the actor name and paper title.
- Step 3: Project entry lists the edited fields.
- Step 4: Entries appear without refresh once the underlying APIs respond.
- Step 6: Deleting a manual discovery result removes it from the list and logs “Related paper deleted” in Updates.

**Rollback**
Revert the temporary project/paper edits or delete the test paper if unnecessary.

**Evidence**
- Capture: `tests/manual/_evidence/2025-09-28_project-updates-feed.png` showing the Updates tab with the four activity cards.
