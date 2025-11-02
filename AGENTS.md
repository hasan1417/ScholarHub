# Repository Guidelines

## Project Structure & Module Organization

* **frontend/** – React (Vite). App entry: `src/` (components, pages, hooks). Dev server: **:3000**.
* **backend/** – FastAPI service. Entry: `app/main.py`; modules under `app/api`, `app/models`, `app/core`.

  * **Python venv:** `backend/scholarenv/` (activate before running backend).
* **docker-compose.yml** (repo root) – infrastructure for **PostgreSQL**, **Redis**, **OnlyOffice**.
* **tests/manual/** – required manual tests. Name as `tests/manual/<area>/<yyyy-mm-dd>_<short-name>.md`.
* **assets/** – screenshots/recordings referenced by tests (e.g., `tests/manual/_evidence/…`).
* **docs/** – short architecture notes and runbooks.

**Ports**: FE **3000**, BE **8000**, Postgres **5432**, Redis **6379**, OnlyOffice **8080**.

## Build, Test, and Development Commands

**Containerized stack (default workflow)**

```bash
docker compose up -d postgres redis onlyoffice
docker compose up -d backend frontend
```

These containers expose the dev servers on :3000 and :8000. Stop any locally running Vite or Uvicorn processes first to avoid port conflicts.

**Start infrastructure only (if you only need databases/services)**

```bash
docker compose up -d postgres redis onlyoffice
```

**Pre‑flight port checks (macOS/Linux)**

```bash
lsof -i :3000 || echo "Port 3000 free"
lsof -i :8000 || echo "Port 8000 free"
```

**Backend (FastAPI) – local venv fallback**

```bash
cd backend
source scholarenv/bin/activate      # Windows: scholarenv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> Do not terminate an existing `uvicorn` process or start it again once it is running; coordinate with the shared backend instead of restarting it.

**Frontend (Vite) – local fallback**

```bash
npm install
npm run dev  # http://localhost:3000
```

**Environment (.env examples)**

```env
VITE_API_BASE_URL=http://localhost:8000
BACKEND_CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
ONLYOFFICE_URL=http://localhost:8080
DATABASE_URL=postgresql://scholarhub:scholarhub@localhost:5432/scholarhub
REDIS_URL=redis://localhost:6379
SECRET_KEY=change-me-in-production
DEBUG=true
```

**Database migrations inside the backend container**

```bash
docker compose exec backend alembic upgrade head
```

## Post-change validation

Match validation to the stack you touched:

- Backend (`*.py` changes): `(source backend/scholarenv/bin/activate && cd backend && pylint app)`
- Frontend (`*.ts`/`*.tsx` changes): `docker compose exec frontend npm run build`

Run both commands if you modified both stacks.

## LaTeX Editor Integration

- Reuse `LatexAdapter`/`LaTeXEditor`; never change their React `key` or create wrapper components that remount the editor per render.
- Sync remote updates with `adapterRef.current?.setContent(...)` or CodeMirror transactions instead of replacing the `value` prop; the adapter already memoizes the host value.
- Wrap editor callbacks in `useCallback` and keep container refs stable (store changing data in `useRef`) so CodeMirror’s DOM is not destroyed on each keystroke.
- Avoid programmatic `blur()` calls while typing; only blur when transitioning to read-only mode and guard it with the existing `readOnly` check.
- When extending the UI (toolbars, sidebars), pass stable props—if focus suddenly drops, inspect the adapter props first for referential churn.

**Manual Test Requirement (Ask before)**

* Every change includes a manual test under `tests/manual/...` with Purpose, Setup, Test Data, Steps, Expected Results, Rollback, and Evidence (`tests/manual/_evidence/`).

**Notes**: Do **not** run dockerized `frontend`/`backend` alongside local servers (port conflicts). No git commands are required in local workflows.
