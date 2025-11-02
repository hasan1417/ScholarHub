# Purpose
- Verify the OnlyOffice rich-text editor mounts without runtime errors for editor/admin roles after the OOAdapter container restructuring.

# Setup
- Dockerized stack running: `docker compose up -d postgres redis onlyoffice backend frontend`
- Admin/editor account with access to a project that has at least one rich-text paper.
- Frontend built with the current changes.

# Test Data
- Existing project ID and paper ID where the paper is authored in rich-text (OnlyOffice) mode.

# Steps
1. Sign in with the admin/editor account.
2. Navigate to `Projects → <project> → Papers` and open the rich-text paper.
3. Click `Open in Editor` (or use the `/editor` route) so `DocumentShell` loads the OnlyOffice adapter.
4. Confirm the toolbar buttons allow editing (e.g., type into the document or toggle bold) and that the OnlyOffice status indicator shows `Editing` instead of `Viewing`.
5. Observe the browser console while the editor initializes.

# Expected Results
- The editor loads to edit mode within a few seconds.
- Typing or formatting is allowed (no read-only banner), reflecting the admin/editor role.
- No `NotFoundError` (or other DOM insertion errors) appear in the console during or after initialization.
- The loading veil disappears once the document renders, and editing controls are available.

# Rollback
- Revert the frontend build/deployment if a blocking error occurs.

# Evidence
- Capture a screenshot of the editor in edit mode with the console showing no errors (`tests/manual/_evidence/2025-10-05_onlyoffice-admin-load.png`).
