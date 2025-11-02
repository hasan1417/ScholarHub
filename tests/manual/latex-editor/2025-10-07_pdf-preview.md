# Purpose
Verify that compiling LaTeX source renders a populated PDF preview in the in-app viewer.

# Setup
- Frontend dev server running at http://localhost:3000 with authenticated session.
- Backend API available at http://localhost:8000.
- Sample LaTeX paper containing bibliography insertion via sidebar helper.

# Test Data
Use the three-page LaTeX template provided in the bug report (includes `\bibliographystyle{plain}` and `\bibliography{main}`).

# Steps
1. Open the LaTeX paper in the ScholarHub editor.
2. Ensure the source contains the `% Bibliography` block inserted by the sidebar helper.
3. Click `Compile` in the toolbar and wait for the status to show `Compiled`.
4. Observe the PDF preview iframe after compilation completes.

# Expected Results
- Compile status transitions to `Compiled` without errors.
- PDF preview displays the rendered three-page document with title page, lorem ipsum body, table, and quadratic equation (no blank pages).

# Rollback
Remove any temporary edits made to the LaTeX source or switch back to another paper; no additional rollback actions required.

# Evidence
Pending capture during interactive session (PDF preview should show rendered content).
