### Purpose
Verify the Paper Detail view uses the refreshed dark-mode tones so its cards and menus match the broader project theme.

### Setup
- Docker stack running with `frontend` and `backend` services (`docker compose up -d postgres redis onlyoffice frontend backend`).
- Test account with access to a project that already contains at least one paper.
- Browser with cached data cleared or hard-refreshed to ensure latest assets load.

### Test Data
- Existing project and paper (no specific content required).

### Steps
1. Sign in and navigate to `/projects/<projectId>/papers`.
2. Switch the global theme toggle to dark mode.
3. Open any paper to load the Paper Detail page.
4. Observe the page header, primary summary cards, team list, keywords list, and references section.
5. Open the “More actions” menu (three dots) in the header and review its background and hover states.

### Expected Results
- Page header uses the same translucent slate tone as other project screens without feeling heavier.
- Summary, activity, team, and keyword cards rest on a slate-800 tinted surface with clear borders.
- Empty states and dashed boxes lighten to a slate-800/40 wash that preserves contrast with surrounding cards.
- List rows (team members, references) sit on solid slate-800 cards with a subtle shadow, keeping role badges and copy legible.
- The actions menu inherits the lighter slate overlay and hover states remain visible in dark mode.

### Rollback
Revert the Paper Detail styling changes in `frontend/src/pages/projects/PaperDetail.tsx` and redeploy the frontend.

### Evidence
- Visual confirmation in browser (no capture stored).
