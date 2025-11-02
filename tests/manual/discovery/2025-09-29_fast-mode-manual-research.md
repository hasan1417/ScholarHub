# Manual Test – Manual Discovery Fast Mode

- **Purpose**: Verify that project-level manual discovery runs exit faster by leveraging the new fast mode orchestration.
- **Setup**:
  - Ensure dockerized backend and frontend are running (`docker compose up -d backend frontend`).
  - Sign in with an account that has an existing project containing at least two papers.
  - Open the ScholarHub web UI at `http://localhost:3000` and navigate to the target project.
- **Test Data**: Use any project whose discovery preferences include a non-empty query (e.g., “graph neural networks”) and leave manual discovery sources at their defaults.
- **Steps**:
  1. Navigate to `Projects → <project> → Discovery` and select the `Manual` tab.
  2. Set `Max results` to `1` and trigger a manual discovery run.
  3. Record the elapsed time shown in the in-app status toast/logs.
  4. Re-trigger the manual run with `Max results = 1` and confirm completion within ~10s.
  5. Trigger another manual run with `Max results = 10` and confirm completion without regressions (may take longer than the fast run but should succeed).
  6. For a project where the first batch of results are already in Related Papers, rerun manual discovery and confirm the system fetches additional candidates (status toast shows >0 results created when new papers exist).
  7. Open the discovery result list and verify that entries reported as Open Access expose a working `View PDF` button (open a few non-arXiv sources to confirm they load the PDF directly rather than the landing page).
- **Expected Results**:
  - Manual runs with `Max results = 1` complete noticeably faster than previous behavior (ideally ≤10s) and return at least one suggestion when available.
  - Longer runs (e.g., `Max results = 10`) still complete successfully, showing that fast mode is scoped to low result counts.
  - Open Access entries provide a functioning direct PDF link (non-ArXiv sources open the PDF without redirecting back to the landing page).
  - No errors appear in the UI or server logs during these runs.
- **Rollback**: Revert the backend changes if regressions are observed and redeploy containers (`docker compose up -d --build backend`).
- **Evidence**: Capture a screenshot of the manual discovery run summary including completion time and place it under `tests/manual/_evidence/2025-09-29_fast-mode-manual-research.png`.
