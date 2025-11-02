# LaTeX Editor Save Control

**Purpose**: Ensure the LaTeX editor Save control continues to persist content via the adapter after prop/type cleanup.

**Preconditions / Setup**
- Infrastructure services running: `docker compose up -d postgres redis onlyoffice`.
- Backend: `cd backend && source ../scholarenv/bin/activate && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
- Frontend: `cd frontend && npm run dev`.
- Logged in as a user with at least one LaTeX-mode paper.

**Test Data**
- Any LaTeX paper ID the tester can edit (e.g., `paper-latex-1`).

**Steps**
1) Navigate to `/papers/<paperId>/edit` for the LaTeX paper.
2) Confirm the Save button appears in the LaTeX toolbar while in edit mode.
3) Edit the LaTeX source (add a comment line).
4) Click **Save** and watch the network panel for the `PATCH /papers/<paperId>` call.
5) Confirm the payload contains `content_json.authoring_mode = "latex"` and the updated source.
6) Refresh the page and verify the edit persists.

**Expected Results**
- Step 2: Save button rendered and enabled.
- Step 4: A single API request fired with HTTP 200.
- Steps 5-6: Updated LaTeX source saved and restored on reload.

**Rollback / Cleanup**
- Remove the added comment manually or by undoing changes.
- Stop dev servers and `docker compose down` when finished.

**Evidence**
- (Not captured; tester to supply screenshot or HAR if required.)
