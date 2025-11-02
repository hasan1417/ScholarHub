# Purpose
Verify that LaTeX-authored papers open in a PDF-only viewer on the paper view route and still allow editors to navigate to the full editor.

# Setup
- Frontend dev server running (via docker compose or `npm run dev`).
- Backend running with access to a LaTeX-enabled paper containing rendered content.
- Log in with:
  - An editor/admin user for the project containing the target paper.
  - A viewer user for sanity check (optional, see Test Data).

# Test Data
- Project ID containing a LaTeX paper (e.g. project formerly failing to show preview).
- Paper ID with `content_json.authoring_mode === "latex"`.

# Steps
1. Navigate to `/projects/<projectId>/papers/<paperId>/view` as an editor.
2. Observe the header controls and the main content area.
3. Wait for the compile banner to report success; if needed, click `Recompile`.
4. Scroll through the PDF to confirm it renders pages correctly.
5. Click `Edit Paper` and press `Compile`; confirm the status banner reports success and the PDF pane refreshes with the new output.
6. (Optional) Repeat step 1 as a viewer and confirm the same PDF-only presentation without edit controls.

# Expected Results
- The page header shows a Back button and the paper title; the body displays only the PDF viewer (no LaTeX code editor).
- The compile banner shows `Preview ready` after the auto compile finishes; manual `Recompile` works without errors.
- PDF pages render end-to-end; no OnlyOffice interface appears.
- `Edit Paper` button opens the LaTeX editor route for authorized roles; viewers do not see the button.

# Rollback
Revert the changes to `frontend/src/components/editor/LatexPdfViewer.tsx` and `frontend/src/pages/projects/ViewPaper.tsx`, then rerun `npm run build` to confirm the old flow restores the OnlyOffice-based viewer.

# Evidence
- N/A (visual confirmation in browser).
