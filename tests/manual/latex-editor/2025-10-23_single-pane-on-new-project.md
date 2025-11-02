## Purpose
Verify that creating a new LaTeX project now renders a single editor pane instead of multiple stacked panes.

## Setup
- Frontend running against development backend (either via `docker compose up frontend backend` or locally with matching `.env`).
- Test account with permission to create projects and papers.

## Test Data
- Use any project workspace; paper content can remain empty.

## Steps
1. Sign in to ScholarHub.
2. Navigate to Projects and create a new LaTeX paper (choose LaTeX authoring mode if prompted).
3. Wait for the editor view to load.

## Expected Results
- Exactly one LaTeX code editor is visible.
- The PDF preview panel (split view) renders to the right when compilation completes.
- No duplicate editor panes with repeated line numbers appear.

## Rollback
- Delete the test paper/project if it is no longer needed.

## Evidence
- Not captured for this run.
