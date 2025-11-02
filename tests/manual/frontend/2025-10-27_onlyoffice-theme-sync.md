### Purpose
Confirm the OnlyOffice editor respects ScholarHub’s theme toggle, staying synchronized across refreshes.

### Setup
- Docker stack running with OnlyOffice and frontend containers (`docker compose up -d postgres redis onlyoffice frontend backend`).
- Account with access to a project document that opens in OnlyOffice mode.
- Browser with access to the global theme toggle.

### Test Data
- Any paper configured for the rich/OnlyOffice editor (content not important).

### Steps
1. Sign in, open a document that launches the OnlyOffice editor.
2. Toggle the global theme to **light** if not already enabled.
3. Reload the page (`Cmd/Ctrl+R`) and wait for OnlyOffice to finish loading.
4. Verify the OnlyOffice chrome (toolbar, canvas, menus) appears in the light theme.
5. Switch the global theme to **dark**.
6. Observe the editor update to the dark theme without a full reload.
7. Refresh again with dark mode active and confirm OnlyOffice loads in dark mode from the start.

### Expected Results
- OnlyOffice theme always matches the selected ScholarHub theme immediately after loading.
- Theme switches apply within the live session (no reload required).
- Repeated refreshes retain the chosen theme—no more random light/dark defaults.

### Rollback
Revert the theme-handling changes in `frontend/src/components/editor/adapters/OOAdapter.tsx` (and related style updates) then redeploy the frontend.

### Evidence
- Visual confirmation in browser (no capture stored).
