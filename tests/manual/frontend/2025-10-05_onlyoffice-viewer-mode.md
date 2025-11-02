# Purpose
- Ensure the project "View" route renders the OnlyOffice editor shell in read-only mode and still lets privileged users jump to the full editor.

# Setup
- Docker stack running (`docker compose up -d postgres redis onlyoffice backend frontend`).
- Paper with rich-text (OnlyOffice) content inside a project.
- Test with:
  - Viewer account (should see read-only view).
  - Admin/editor account (should see read-only view plus "Edit" button).

# Test Data
- Project ID and paper ID from an existing OnlyOffice-based paper.

# Steps
1. Sign in as a user with `viewer` role on the project.
2. Navigate to `/projects/<projectId>/papers/<paperId>/view`.
3. Confirm the OnlyOffice interface appears and the document loads.
4. Attempt to type or use formatting controls—verify they are disabled and the References/Chat sidebar toggle is not available.
5. Sign in as an admin/editor for the same project and repeat steps 2-3.
6. Confirm the interface still shows read-only mode, the sidebar toggle remains hidden, and an "Edit Paper" button appears in the top-right overlay.
7. Click "Edit Paper" and ensure it routes to the `/editor` page with full edit access (full editor regains the sidebar).

# Expected Results
- Viewer sees OnlyOffice UI with "Viewing" indicator; editing controls are inactive and the sidebar toggle is absent.
- Admin/editor sees the same read-only UI plus an "Edit Paper" button that opens the editor route (full editor re-enables sidebar tools).
- No console errors appear while loading.

# Rollback
- Revert to previous frontend build if loading fails or editing cannot be restored.

# Evidence
- Screenshot of the read-only OnlyOffice view (viewer account) and optional screenshot after clicking "Edit Paper" to show the editor route (`tests/manual/_evidence/2025-10-05_onlyoffice-viewer-mode.png`).
