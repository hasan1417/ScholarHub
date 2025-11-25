# Purpose
Verify that the Papers section blocks duplicate titles within the same project/workspace and surfaces useful UI errors.

# Setup
1. Backend API and frontend dev server running (per README workflow).
2. Sign in with a user who can create papers inside a project.
3. Navigate to a project that already contains at least one paper (or create one with a unique title to start).

# Test Data
- Existing paper title to reuse: e.g., “Thermal Interfaces Study”.
- Optional: a second title for control, e.g., “Thermal Interfaces Study v2”.

# Steps
1. From the project’s Papers tab, open “Create New Paper”.
2. Enter the exact title of the existing paper; the “Create Paper” button should disable automatically and a red helper message should appear before you can submit.
3. Attempt to click “Create” (should remain disabled) until you change the text; once the title is unique, the button re-enables.
4. Repeat the test via the “Create with template” flow (Projects → Papers → “Create with template”) and confirm the inline warning prevents the button from enabling; also verify you must choose a paper type/template and select one or more existing objectives (checkbox list) before the button re-enables.
5. (Optional) Try renaming an existing paper to another title that already exists in the same project via the paper editor; confirm the API call fails (toast/error) and the title remains unchanged.
6. Change the title to a unique value and confirm creation/update succeeds, with the selected objective stored on the paper card.

# Expected Results
- The frontend disables submission when a duplicate title is detected, showing a red helper message (workspace wording for standalone, “this project” for project-scoped creation).
- Even if you bypass the UI, the backend still rejects duplicate titles with HTTP 409.
- The objective picker enforces at least one selection; it only lists objectives already stored on the project.
- Once a unique title is provided, creation succeeds and the paper opens as usual, showing all linked objectives on the project card.

# Rollback
- Delete any temporary papers created during the tests so the project stays clean.

# Evidence
- Capture screenshots of the inline error states if needed (`tests/manual/_evidence/2025-11-12_paper-title-uniqueness.png`).
