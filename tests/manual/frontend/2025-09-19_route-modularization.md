# Frontend Route Modularization

**Purpose**: Verify that modularized service routes render the expected views after the routing refactor and that primary navigation paths remain functional.

**Preconditions / Setup**
- Dev mode: Local FE/BE; infra via Docker.
- Services: FE http://localhost:3000, BE http://localhost:8000, OnlyOffice http://localhost:8080, DB 5432, Redis 6379.
- Seed/Accounts: Use an existing development account with researcher permissions (e.g., `dev@example.com`).
- Flags: Default `.env` values; no feature flags changed.

**Test Data**
- Email: `dev@example.com`
- Password: `<dev-password>`

**Steps**
1) Start infra: `docker compose up -d postgres redis onlyoffice`.
2) In `backend/`, run `uvicorn app.main:app --reload --host 0.0.0.0 --port 8000`.
3) In `frontend/`, run `npm run dev` and open http://localhost:3000/login.
4) Log in with the dev credentials and confirm the dashboard renders at `/`.
5) Use the navigation header to visit `/papers`, `/my-references`, and `/discovery`; ensure each route loads without reloads.
6) Manually visit `/prototypes/onlyoffice` and `/publisher-probe` via the address bar; confirm each specialized module renders.
7) Log out via the header and confirm the app redirects back to `/login`.

**Expected Results**
- Step 3: Login page rendered from the auth route module.
- Step 4: Protected layout loads and dashboard content displays within `Layout`.
- Step 5: Papers, references, and discovery pages render correctly with existing data lists.
- Step 6: Prototype and debug routes render without 404; console shows no routing errors.
- Step 7: Logout clears session and redirects to `/login`.

**Rollback / Cleanup**
- Stop frontend and backend servers (`Ctrl+C`).
- Run `docker compose down` to stop infra containers.

**Evidence**
- `../_evidence/2025-09-19_route-modularization.png`
