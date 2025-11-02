# Manual Test - Discovery OA Verification

## Purpose
Confirm that discovery results no longer flag paywalled sources as open access when no downloadable PDF is available.

## Setup
- Backend and frontend containers running via `docker compose up -d backend frontend`.
- Backend virtualenv activated for ad-hoc service checks (`source backend/scholarenv/bin/activate`).

## Test Data
- Query: `"Modelling social action for AI agents"` (previously produced a false OA flag for Elsevier).
- Sources: `openalex` only.

## Steps
1. From `backend/`, run the async script below to execute discovery for the target query:
   ```bash
   source scholarenv/bin/activate
   python - <<'PY'
   import asyncio
   from app.services.paper_discovery_service import PaperDiscoveryService, PaperSource

   async def run():
       service = PaperDiscoveryService()
       try:
           papers = await service.discover_papers(
               query="Modelling social action for AI agents",
               max_results=5,
               sources=[PaperSource.OPENALEX.value],
           )
           for idx, paper in enumerate(papers, start=1):
               print(idx, paper.title)
               print(" pdf_url:", paper.pdf_url)
               print(" is_open_access:", paper.is_open_access)
               print(" open_access_url:", paper.open_access_url)
               print("---")
       finally:
           await service.close()

   asyncio.run(run())
   PY
   ```
2. Review the printed discovery output.

## Expected Results
- The Elsevier result (`Modelling social action for AI agents`) should show `pdf_url: None` and `is_open_access: False`.
- No `View PDF` link should be offered for paywalled records.

## Rollback
No rollback required.

## Evidence
- `tests/manual/_evidence/2025-09-30_discovery_oa_verification.txt`
