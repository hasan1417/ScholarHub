# Active Feed Preferences

## Purpose
Verify that active search feed preferences live entirely in the Active tab while manual runs operate on ad-hoc overrides, showing an informative message when no new results are found.

## Setup
- Frontend dev server running (`npm run dev` or docker compose frontend) with refreshed build.
- Backend running with latest project discovery changes.
- Project that already has historical discovery results.

## Test Data
- Use project `ScholarHub Sample Project` (ID 7ce05847-1dc3-4ebb-b930-0b093ee63f3e).

## Steps
1. Open the project and go to `Project Discovery`.
2. Switch to `Active search feed` tab.
3. Confirm the "Active feed preferences" panel shows query, read-only project keywords, max results, relevance threshold, auto-refresh toggle, refresh interval, and source checkboxes.
4. Change the refresh interval to `45`, deselect one source, and click `Save preferences`. Ensure the success toast shows.
5. Reload the page; confirm the saved values persist.
6. Switch to `Manual discovery` tab, set `Max results` to `1`, and run `Run Discovery`.
7. Verify that, when no new manual results appear, a banner states "No new discovery results — everything in your project already matches this search." and the manual results list stays empty.
8. Adjust the query to something broader, run again, and confirm new manual results appear without the banner.

## Expected Results
- Active tab renders preference controls, saves successfully, and retains values after reload.
- Manual tab shows no project-context banner; manual keywords stay read-only.
- If manual run yields zero new results, the informational banner appears and the list stays empty.
- If manual run finds new results, the banner disappears and the new entries appear under Manual results.

## Rollback
- Restore original Active preferences by re-enabling the removed source and saving.

## Evidence
- Screenshot of the Manual tab showing the "No new discovery results" banner.
- File: `tests/manual/_evidence/2025-09-29-no-new-results.png`.
