# Manual Test - Discovery PDF Extraction (BOA Unimib)

## Purpose
Confirm discovery correctly surfaces the direct PDF link for BOA (boa.unimib.it) records instead of echoing the handle URL.

## Setup
- Docker stack running; backend container already rebuilt with latest service changes.
- Use backend virtualenv inside container (`docker compose exec backend bash -lc "source scholarenv/bin/activate"`).

## Test Data
- Query: `"The need to move away from agential-AI"`
- Source: `openalex`

## Steps
1. Run the snippet inside the backend container to execute discovery directly:
   ```bash
   docker compose exec backend bash -lc "source scholarenv/bin/activate && python - <<'PY'
   import asyncio
   from app.services.paper_discovery_service import PaperDiscoveryService, PaperSource

   async def run():
       service = PaperDiscoveryService()
       try:
           papers = await service.discover_papers(
               query='The need to move away from agential-AI',
               max_results=1,
               sources=[PaperSource.OPENALEX.value],
               fast_mode=False,
           )
           p = papers[0]
           print('pdf_url:', p.pdf_url)
           print('open_access_url:', p.open_access_url)
       finally:
           await service.close()

   asyncio.run(run())
   PY"
   ```
2. Observe the printed `pdf_url` and `open_access_url` values.

## Expected Results
- `pdf_url` resolves to `https://boa.unimib.it/retrieve/.../IJHCS-D-21-00252-R1.pdf` (direct PDF).
- `open_access_url` remains the handle `http://hdl.handle.net/10281/324837`.
- No exceptions raised.

## Rollback
No rollback required.

## Evidence
- `tests/manual/_evidence/2025-09-30_discovery_boa_pdf.txt`
