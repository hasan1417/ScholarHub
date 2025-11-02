# Manual Test - Sync Space Tab Placeholder

**Purpose**
Verify the new Sync Space tab appears within the project workspace and displays the introductory layout for upcoming meeting features.

**Setup**
1. Backend running locally (`uvicorn app.main:app --reload`).
2. Frontend dev server running (`npm run dev`).
3. Authenticated user with access to an existing project.

**Steps**
1. Navigate to `http://localhost:3000/projects/<projectId>`.
2. Ensure the main navigation bar now lists `Sync Space` between `Discovery` and `Related Papers`.
3. Click the `Sync Space` tab and confirm the route changes to `/projects/<projectId>/sync-space`.
4. Validate the page shows the hero card with the **Start a sync** button and the three informational panels.
5. Refresh the browser; confirm the Sync Space route loads directly without navigation errors.

**Expected Results**
- Step 2: `Sync Space` appears as a top-level tab for all non-viewer roles (viewers should still see it alongside other tabs except Discovery).
- Step 3: Clicking the tab swaps content without a full page reload.
- Step 4: The placeholder sections render with icons and descriptive copy, indicating upcoming meeting capabilities.
- Step 5: Direct navigation preserves the layout and no console errors are thrown.

**Rollback**
None required.

**Evidence**
- Optional screenshot of the Sync Space layout after navigation.
