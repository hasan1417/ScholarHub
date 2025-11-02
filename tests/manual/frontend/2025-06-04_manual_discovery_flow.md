# Manual Discovery Flow Test

## Purpose
Validate the Discovery workspace: saving preferences, running manual discovery, clearing dismissed items, and managing existing results.

## Setup
1. Backend running locally (`uvicorn app.main:app --reload`).
2. Frontend dev server running (`npm run dev`).
3. Log in with a project that has discovery enabled (e.g., `g202403940@kfupm.edu.sa / testpass123`).
4. Ensure the database has been migrated to the latest revision (`alembic upgrade head`).

## Test Data
- Project ID: any accessible project (sample: `c9116a31-d03d-4896-aa35-c26c59f288c2`).

## Steps
1. Open the project workspace and click the new **Discovery** tab.
2. In “Manual discovery,” set:
   - Query: `literature review automation`
   - Keywords: `AI, collaboration`
   - Check `Semantic Scholar`, `arXiv`, and `Crossref` sources.
   - Set max results to `5` and relevance threshold to `0.5`.
3. Click **Save preferences** and watch for the success toast.
4. Click **Run Discovery** and wait for the run to finish (spinner disappears and new results load if available).
5. Confirm that only results from the latest run are shown (older manual results are purged automatically).
6. If historical manual results exist after the run, approve the first pending result using **Add to project**; otherwise, confirm the empty state messaging reads “No manual runs recorded for this project yet.”
7. Dismiss another result using **Dismiss**.
8. Switch the status filter pill to **Dismissed**, then click **Clear dismissed** and confirm the list re-fetches with no dismissed entries.
9. Refresh the list via the **Refresh** button and verify statuses update (promoted/dismissed chips).
10. Navigate back to **Related Papers** and confirm the promoted reference appears as pending/approved accordingly.
11. Return to **Discovery** and ensure the badge in the tab reflects the remaining pending count.

## Expected Results
- Preferences save without error and repopulate on reload.
- Manual discovery exposes a **Run Discovery** button that triggers a backend run, purges older manual results, and refreshes the list.
- Approving a result marks it as promoted and attaches/updates the project reference (if results exist).
- Dismissing a result marks it dismissed and removes it from the pending badge.
- Discovery tab badge decrements after actions; Related Papers reflect promoted items.
- Empty state copy reads “No manual runs recorded for this project yet.” when no historical data is present.
- Switching to the **Dismissed** filter exposes the **Clear dismissed** action, which removes the dismissed list and shows the success banner.

## Rollback
- Optionally reset preferences to previous state and clear promoted/dismissed references if needed.

## Evidence
- Screenshot of Discovery tab confirming the navigation button and any pending items.
- Screenshot of Related Papers list highlighting the newly approved reference.
- Network inspector capture for `/discovery/preferences`, `/discovery/run`, `/discovery/results/.../promote`, and `/discovery/results/dismissed` requests.
