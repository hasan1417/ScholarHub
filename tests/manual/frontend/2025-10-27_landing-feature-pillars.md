### Purpose
Validate that the landing page highlights Discovery, Sync Space, and Paper Status pillars tailored to lab leads.

### Setup
- Frontend running with fresh assets (`docker compose up -d frontend`).
- Browser in incognito/private mode to avoid cached bundle.

### Test Data
- None required; static copy only.

### Steps
1. Visit `http://localhost:3000/` while signed out.
2. Scroll to the “Run your lab from a single command center” section.
3. Verify the three feature cards read “Library Discovery feed”, “Meeting Sync Space”, and “Paper status at a glance”.
4. Confirm each card includes the updated descriptions referencing lab operations (auto surfaced papers, meeting notes/follow-ups, drafting milestones).
5. Ensure the section subheading copy mentions rolling discovery, meeting operations, and paper health into one dashboard.

### Expected Results
- Section heading reads “Run your lab from a single command center”.
- Supporting paragraph states ScholarHub unifies discovery, meeting operations, and paper health for lab leads.
- All three cards display the new titles and descriptions without visual regressions in light mode.

### Rollback
Revert landing feature updates in `frontend/src/pages/Landing.tsx` and redeploy the frontend.

### Evidence
- Visual confirmation in browser (no capture stored).
