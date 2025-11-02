# Manual Test - Project Editing from List and Detail Views

**Purpose**
Verify that projects can be edited from the projects list and from the project detail header, and that updates persist across views.

**Setup**
1. Frontend dev server running (`npm run dev`).
2. Backend running; user authenticated with existing projects seeded.

**Test Data**
- Choose a project with visible title, idea, scope, and keywords to edit (or create one first).

**Steps**
1. Navigate to `http://localhost:3000/projects`.
2. In grid view, click `Edit` on any project card.
3. Change the title suffix (e.g., add `- Edited`), adjust scope, and modify keywords; save changes.
4. Confirm the card reflects the new title and scope, and keywords update after the refresh spinner completes.
5. Switch to table view, click `Edit` on the same project, change the idea text, and save; verify the row updates.
6. Open the project (`Open` → detail page) and click `Edit project` in the header.
7. Update title/idea/scope/keywords again, save, and ensure the header and overview sections show the new values.
8. Return to the project list and verify the list uses the latest details.

**Expected Results**
- Steps 2–4: Edit modal pre-populates current data; saving succeeds, modal closes, and list shows new values.
- Step 5: Table row updates after edit without needing a manual reload.
- Steps 6–7: Header edit modal mirrors list modal; saving refreshes the page data with no console errors.
- Step 8: Project list reflects all updates.

**Rollback**
Reopen the edit modal and revert the project fields to their original values if necessary.

**Evidence**
- None captured (changes observed in UI).
