# Manual Test - Discovery Dismissed Cleanup

**Purpose**
Validate that the Discovery workspace can bulk-clear dismissed suggestions and that the UI refreshes accordingly.

**Setup**
1. Backend running locally (`uvicorn app.main:app --reload`).
2. Frontend dev server running (`npm run dev`).
3. Authenticated user with access to a project containing discovery preferences and at least one historical result.

**Test Data**
- Project ID with existing discovery settings (example: `c9116a31-d03d-4896-aa35-c26c59f288c2`).

**Steps**
1. Navigate to `http://localhost:3000/projects/<projectId>/discovery` and confirm the Manual discovery tab is active.
2. Click **Run Discovery** to queue a new manual search (skip if recent results already exist).
3. Dismiss at least one suggestion via **Dismiss** to populate the dismissed list.
4. Switch the status filter pills to **Dismissed** and verify the new `Clear dismissed` button appears.
5. Click **Clear dismissed** and wait for the spinner to complete.
6. Confirm the list refreshes with no dismissed entries and the success banner reads “Dismissed discovery results cleared.”

**Expected Results**
- Dismissing a result moves it into the dismissed view without errors.
- The **Clear dismissed** button triggers a backend cleanup and removes all dismissed rows for the project.
- After clearing, the dismissed list is empty and the informational banner is displayed.

**Rollback**
None required.

**Evidence**
- Optional screenshot of the dismissed view before/after clearing.
