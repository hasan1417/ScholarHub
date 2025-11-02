# Related Papers Header Actions

## Purpose
Ensure the compact header controls behave as expected: `Upload PDF` button (when needed), `PDF on file` pill, and Delete icon.

## Setup
1. Latest containers running: `docker compose up -d --build backend frontend`.
2. Frontend at http://localhost:3000 with an authenticated editor.
3. Have at least one related paper with no stored PDF and one with a processed PDF.

## Test Data
Any project reference will do; optional dummy PDF (≤5 MB) for upload testing.

## Steps
1. Open the Related Papers tab.
2. Tab through a card: title → badges → Upload PDF button (or PDF on file pill) → Delete icon. Ensure focus outlines appear.
3. For a card lacking a PDF, click `Upload PDF`; verify the file picker opens and the button shows `Uploading…` until complete. Cancel if you’re not adding a file.
4. For a card with a stored PDF, confirm the pill reads `PDF on file` and no upload button is visible.
5. Hover/click Delete to trigger the confirmation modal; cancel once, then confirm deletion and verify the Undo toast restores the entry.
6. Repeat steps 3–5 using keyboard activation (Enter/Space) to confirm accessibility.

## Expected Results
- `Upload PDF` button appears only when no PDF is stored and shows a loading label while uploading.
- `PDF on file` pill displays for stored PDFs; viewing still handled via the Source link lower in the card.
- Delete flow stays unchanged with modal + Undo toast.
- All controls meet the ≥36 px target and retain visible focus/hover states.

## Rollback
If the controls don’t behave as expected, redeploy the previous frontend image and revert the markup changes.

## Evidence
Screenshot of both states (Upload button vs PDF on file) plus console/toast capture after Delete/Undo.
