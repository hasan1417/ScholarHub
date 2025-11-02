# Viewer Discovery Access Restriction

## Purpose
Verify that project members with the Viewer role cannot access the Discovery tab or create new project papers.

## Setup
- Backend and frontend running locally with seeded project data.
- Test account added to a project with role `viewer` and accepted membership status.

## Test Data
- Project containing at least one admin and the viewer account above.

## Steps
1. Sign in as the viewer user and open the project overview.
2. Inspect the project navigation pills at the top of the page.
3. Confirm the "New paper" button is absent on the Project Papers tab.
4. Attempt to navigate directly to `/projects/<project-id>/discovery` via the browser address bar.
5. Switch back to an admin account and confirm both the Discovery tab and "New paper" button appear and function normally.

## Expected Results
- Viewer does not see the Discovery navigation pill or the "New paper" button.
- Direct navigation to the discovery route redirects the viewer to the Related Papers tab (or another allowed page).
- Admin retains full access to the Discovery tab and paper creation flow.

## Rollback
No rollback required.

## Evidence
- `tests/manual/_evidence/2025-03-07_project-viewer-discovery-access.png`
