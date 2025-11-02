# Manual Test - Project Discovery Manual & Active Feed

**Purpose**
Validate the discovery hub configuration flow, confirm navigation to the Papers overview from Manual discovery, and ensure the active search feed hydrates defaults while filtering out suggestions already present in Related Papers.

**Setup**
1. Frontend dev server running (`npm run dev`).
2. Backend running with discovery endpoints available and a logged-in user.
3. Choose a project with existing metadata (title, idea, keywords) and some discovery history.

**Test Data**
- Project ID used for discovery regression (e.g., `c9116a31-d03d-4896-aa35-c26c59f288c2`).
- Ensure the project has at least one saved related-paper suggestion to verify deduplication.

**Steps**
1. Navigate to `http://localhost:3000/projects/<projectId>/discovery`.
2. Ensure the page defaults to the **Manual discovery** tab; note the context banner showing project idea/keywords, the read-only keyword panel, and that sources are pre-selected.
3. Click `Run Discovery` to ensure a manual run can still be triggered and note any new manual results.
4. Enable `Enable active search feed (auto-refresh)` and set interval to `12` hours; save preferences.
5. Refresh the page, verify the tab selection persists, then switch to the **Active search feed** tab and confirm the toggle, interval, and sources persisted.
6. In the Active tab, check the status filter pills and confirm the banner shows `Auto-refresh every 12h`; if duplicates exist, the amber banner should report them as hidden.
7. Switch the status filter to **Dismissed**, click **Clear dismissed**, and confirm the list refreshes with no dismissed entries.
8. Promote one auto-feed suggestion from the Active tab and ensure it disappears after a manual refresh.

**Expected Results**
- Step 2: Project idea/keywords displayed; sources checked by default.
- Step 3: Manual run executes without errors and updates the list when new results are available.
- Step 4-5: Saving preferences persists auto-refresh state and interval across reload.
- Step 6: Active feed shows only suggestions not already in Related Papers (banner indicates hidden duplicates when applicable).
- Step 7: Dismissed filter exposes the clear action and removes any dismissed items for the project.
- Step 8: Promoted suggestion no longer appears after refresh.

**Rollback**
Revert discovery preferences via UI (disable auto-refresh, clear query adjustments) if necessary.

**Evidence**
- None captured (UI interactions confirmed manually).
