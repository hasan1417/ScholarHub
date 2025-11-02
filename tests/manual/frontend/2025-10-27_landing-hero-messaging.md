### Purpose
Confirm the landing hero speaks directly to graduate researchers, lab leads, and institutional stakeholders, and that the new supporting line renders correctly.

### Setup
- Frontend running (`docker compose up -d frontend`) with no cached asset overrides.
- Browser in incognito/private mode to avoid stale bundle.

### Test Data
- None required; copy loads from static bundle.

### Steps
1. Visit `http://localhost:3000/` while signed out.
2. Observe the hero headline, subhead, and the new multi-snapshot hero above the primary CTA.
3. Confirm only one primary CTA button is rendered.
4. Switch the global theme toggle (if available on this view) and verify text remains legible.

### Expected Results
- Headline reads “Ship papers faster with one workspace for your lab”.
- Subhead promises alignment for PIs, postdocs, and grad researchers across LaTeX, rich editing, AI drafting, meetings, and discovery.
- Hero collage shows the rich editor centered with secondary panels (project overview and discovery) and the caption “Rich editor, project overview, and discovery snapshots keep manuscripts, team context, and literature in view.”
- Only the “Get started free” CTA button is present; no additional trust badges or secondary CTAs are displayed.

### Rollback
Restore the previous hero copy in `frontend/src/pages/Landing.tsx` and redeploy the frontend.

### Evidence
- Visual confirmation in browser (no capture stored).
