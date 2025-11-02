# Legacy Editor Prune

**Purpose**: Confirm the removal of unused prototype/editor modules leaves the active editor experience intact.

**Preconditions / Setup**
- Dev mode: Local FE/BE; infra via Docker.
- Services: FE http://localhost:3000, BE http://localhost:8000, OnlyOffice http://localhost:8080, DB 5432, Redis 6379.
- Seed/Accounts: Existing researcher account (e.g., `dev@example.com`).

**Test Data**
- Email: `dev@example.com`
- Password: `<dev-password>`

**Steps**
1) Start infra: `docker compose up -d postgres redis onlyoffice`.
2) Run backend: `cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
3) Run frontend: `cd frontend && npm run dev`, open http://localhost:3000/login, and sign in.
4) Open `/papers`, choose an existing paper, and click “Edit” to launch the current editor (OnlyOffice or LaTeX depending on paper mode).
5) Verify editing, comments, branching, and presence drawers still render; open `/discovery` to ensure unrelated routes work.
6) Open the browser console to confirm no missing-module or import errors appear.

**Expected Results**
- Steps 3-5: Editor UI operates normally; missing prototype code does not affect live routes.
- Step 6: Console remains free of module resolution errors.

**Rollback / Cleanup**
- Stop dev servers (`Ctrl+C`) and `docker compose down`.

**Evidence**
- `../_evidence/2025-09-19_legacy-editor-prune.png`
