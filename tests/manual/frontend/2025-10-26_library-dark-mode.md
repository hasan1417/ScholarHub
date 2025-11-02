## Purpose
Validate the project Library experience (Discovery + References) renders correctly in dark mode while still looking good in light mode.

## Setup
- Frontend running with theme toggle accessible.
- Project populated with Discovery results and approved references; if empty, trigger a manual discovery run to seed entries.

## Test Data
- At least one manual discovery result (pending/promoted) and an active search feed entry.
- Approved reference with PDF/upload options to exercise action buttons.

## Steps
1. Navigate to `Collaborate → Library → Discover`, toggle between light/dark, and review the manual/active discovery cards, status pills, and inputs.
2. Run a manual discovery or change filters to surface result cards; confirm badges, select/delete states, and list backgrounds adapt in dark mode.
3. Switch to `References`, inspect the list, delete toast, and empty state under both themes.
4. Open the “Add related paper” modal (optional) to ensure its fields respect the theme styling.
5. Verify toast notifications (undo delete) remain legible and contrast appropriately.

## Expected Results
- Library container, sub-tabs, and cards adopt slate tones in dark mode with readable text and interactive hover states.
- Discovery badges (status, score, unsaved changes) retain color meaning without clashing against dark surfaces.
- Reference list pills, action buttons, and summaries stay legible; delete/upload controls remain discoverable.
- Empty/loading states use muted dark backgrounds rather than bright white.

## Rollback
- If you created test discovery runs or references, remove them when finished to keep data tidy.

## Evidence
- Not captured for this run.
