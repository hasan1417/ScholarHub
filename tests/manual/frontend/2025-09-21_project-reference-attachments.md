# Project Reference Attachments

## Purpose
Verify that paper references are managed exclusively through project related papers and can be attached to multiple papers.

## Setup
- Frontend dev server running (`npm run dev`).
- Logged in as a user with editor access to project `c9116a31-d03d-4896-aa35-c26c59f288c2`.
- Project has at least one approved related paper (project reference) and at least one paper.

## Test Data
- Project ID: `c9116a31-d03d-4896-aa35-c26c59f288c2`
- Two papers within the project that can share attachments.

## Steps
1. Open `/projects/<projectId>/papers/<paperId>` and view the “Attached Related Papers” panel.
2. Click “Attach related paper” and select an approved project reference, then save.
3. Confirm the selected reference appears in the list with the correct metadata and detach control.
4. Navigate to the paper editor (`/projects/<projectId>/papers/<paperId>/editor`) and open the references sidebar.
5. Verify the references sidebar lists the same attachment and use “Manage attachments” to attach another related paper.
6. Switch to a different paper in the same project, open its sidebar, and attach the same project reference.
7. Return to the first paper and detach the shared reference using the detach control.

## Expected Results
- Step 1 shows no legacy UI for discovery or manual reference creation.
- Step 2 attaches the project reference without errors.
- Step 3 shows the attached item with detach option (or marked as legacy if it cannot be managed).
- Step 5 reflects the attachment list after the modal save and retains bibliography functionality.
- Step 6 confirms the same project reference can attach to multiple papers.
- Step 7 removes the reference from the first paper while leaving it attached to the second.

## Rollback
Detach any test attachments to restore the original state if needed.

## Evidence
- Verified manually in the browser (no screenshots captured).
