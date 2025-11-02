# LaTeX Editor Focus

**Purpose**: Verify that typing in the LaTeX editor keeps the caret focused after each key press.

**Preconditions / Setup**
- Dev mode: Local FE/BE; infra via Docker.
- Services: Frontend at http://localhost:3000, backend at http://localhost:8000, OnlyOffice at http://localhost:8080.
- Logged in as a research user with an existing LaTeX-mode paper (authoring_mode = `latex`).

**Test Data**
- Paper ID: use any LaTeX paper in the account (e.g., `paper-latex-1`).

**Steps**
1) Start infra: `docker compose up -d postgres redis onlyoffice`.
2) Run backend: `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
3) Run frontend: `cd frontend && npm run dev`.
4) In the browser, log in and navigate to the LaTeX paper’s `/papers/{id}/edit` route.
5) Click inside the LaTeX editor body and hold a key (e.g., type `abc` quickly).
6) Confirm the caret remains in the editor and characters continue to appear without refocusing.
7) Toggle to another UI component (e.g., open the sidebar, close it) and repeat step 5 to ensure focus persists.

**Expected Results**
- Step 5/6: The caret stays active; no extra click is needed between keystrokes.
- Step 7: Focus still persists after UI interactions.

**Rollback / Cleanup**
- Optional: discard test characters with undo.
- Stop dev servers and `docker compose down` when finished.

**Evidence**
- `../_evidence/2025-09-19_latex-editor-focus.png`
