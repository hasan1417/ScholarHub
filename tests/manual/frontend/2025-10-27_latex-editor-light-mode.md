### Purpose
Ensure the LaTeX editor honors both light and dark themes, including toolbar controls, editor chrome, and preview panes.

### Setup
- Docker stack running (`docker compose up -d postgres redis onlyoffice frontend backend`).
- Test account with access to a project containing a LaTeX paper (or ability to create one).
- Browser with theme toggle visible in the app header.

### Test Data
- Existing LaTeX paper is sufficient; content body can remain minimal.

### Steps
1. Sign in and open any LaTeX-authored paper (URL like `/projects/<projectId>/papers/<paperId>/edit`).
2. Switch the global theme toggle to **light**.
3. Observe the LaTeX editor header, toolbars, code pane, and PDF preview.
4. Trigger the tone menu (select text → Tone) and confirm the popover matches the light theme.
5. Toggle the global theme to **dark**.
6. Repeat Step 3 to ensure dark styling still matches prior appearance.
7. Compile the document to populate the logs and confirm both themes keep log surfaces legible.

### Expected Results
- In light mode the editor chrome uses slate/indigo tints on white surfaces; buttons and badges have readable text and hover states.
- Tone and AI menus adopt light borders/backgrounds without reverting to dark tones.
- Code and preview panes show light backgrounds with subtle borders; compile logs use a light table surface.
- Switching to dark mode restores the established dark styling with no regressions.

### Rollback
Revert the theme-related class changes in `frontend/src/components/editor/LaTeXEditor.tsx` and redeploy the frontend.

### Evidence
- Visual confirmation in browser (no capture stored).
