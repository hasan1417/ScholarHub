# Purpose
Confirm OpenAlex results no longer expose false "PDF available" or open-access indicators when the linked PDF cannot be retrieved (manual discovery mode).

# Setup
- Backend + frontend containers rebuilt and running via `docker compose up -d --build backend frontend`.
- Frontend assets rebuilt with `npm run build`.
- Browser pointed at local ScholarHub instance with a project that has discovery enabled.

# Test Data
- Project ID used in local environment: any project with manual discovery access.
- Example DOI to reproduce issue: `10.1016/S0966-842X(00)01913-2` (OpenAlex result without accessible PDF).

# Steps
1. Open the project discovery page and trigger a manual discovery run limited to OpenAlex and the above DOI/keywords.
2. Wait for the run to finish; ensure the result for "Mechanisms of biofilm resistance to antimicrobial agents" appears.
3. Inspect the result card in the manual discovery tab.
4. Repeat steps 1-3 with another OpenAlex record lacking a retrievable PDF (e.g., Nature DOI `10.1038/138032a0`).
5. Promote a discovery result that includes a verified PDF (e.g., an arXiv paper) and, after promotion, inspect the project references list to confirm the entry shows as processed (status `analyzed` or summary populated).

# Expected Results
- Result rows have `PDF available` and `Open access` chips hidden for those DOIs.
- No `View PDF` button is rendered; only `View Source` remains.
- Other sources with valid, reachable PDFs continue to display the PDF badge and button.
- Project discovery history entries (auto/manual tabs) update to remove legacy `View PDF` links once the run completes.
- Promoted references with verified PDFs now show processed metadata (status `analyzed`, summary populated, or internal download path available).

# Rollback
- Revert the backend changes under `app/services/paper_discovery_service.py` if regression is observed.
- Rebuild backend/frontend containers after reverting.

# Evidence
- Manual verification in local environment (no screenshots captured).
