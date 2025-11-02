# Manual Test - Related Papers Route Rename

**Purpose**
Confirm the project "Related Papers" tab matches the new `/related-papers` route and renders the reference suggestions view.

**Setup**
1. Frontend dev server running (`npm run dev`).
2. Backend available with seeded project data and authentication session.

**Test Data**
- Existing project with ID used previously in discovery tests (e.g., first project returned from `/api/v1/projects`).

**Steps**
1. Navigate to `http://localhost:3000/projects` and open any project.
2. Observe the navigation pills; locate "Related Papers".
3. Click "Related Papers".
4. Watch the browser address bar.
5. Verify the related-paper suggestion UI loads without routing errors.

**Expected Results**
- Step 2: "Related Papers" pill is present.
- Step 3/4: URL updates to `/projects/<id>/related-papers`.
- Step 5: Existing "Related papers" content (suggestions list, refresh button, etc.) renders normally.

**Rollback**
No rollback required; route rename is non-destructive.

**Evidence**
- None captured (UI rendered as expected).
