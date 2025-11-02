# Discovery Source Selection Checkbox Test

## Purpose
Verify that discovery sources can be configured via checkboxes and persist through saves and manual runs.

## Setup
1. Ensure the backend is running locally (`uvicorn app.main:app --reload`).
2. Ensure the frontend dev server is running (`npm run dev`).
3. Log in with an account that can access project `c9116a31-d03d-4896-aa35-c26c59f288c2` (example credentials: `g202403940@kfupm.edu.sa` / `testpass123`).

## Test Data
- Project: any project with discovery enabled (sample above).

## Steps
1. Open the project workspace and navigate to the “Related Papers” tab.
2. In “Discovery preferences,” observe current source selections.
3. Check `Semantic Scholar`, `arXiv`, `Crossref`, and `ScienceDirect`; uncheck any other sources.
4. Click `Save preferences` and wait for the success message; in the network tab ensure the `PATCH /discovery/preferences` payload contains only the checked providers.
5. Refresh the page to confirm the same sources remain selected.
6. Click `Run Discovery`; in the network tab inspect the `POST /discovery/run` payload and confirm the `sources` array includes only the checked providers.

## Expected Results
- Previously saved sources render as checked when the page loads.
- Saving updates persists the checkbox selections across page refreshes.
- The saved preferences request includes only the checked sources.
- Manual runs submit the selected sources in the `POST /discovery/run` payload.
- When PubMed is selected, returned cards include at least one item with `source` shown as `pubmed` (assuming results are available).
- When ScienceDirect is selected, at least one result arrives with `source` displayed as `sciencedirect` and links back to Elsevier.

## Rollback
- Restore any prior source selections by toggling checkboxes back to their previous state and saving.

## Evidence
- Screenshot of the Discovery preferences section with the updated checkboxes.
- Screenshot (or HAR entry) showing the `PATCH /discovery/preferences` payload including the expected `sources` array.
