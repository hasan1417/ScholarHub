## Purpose
Ensure the paper editor experience (loading/error states, LaTeX shell, and rich-text flow) renders legibly in dark mode.

## Setup
- Frontend running with theme toggle accessible.
- Project containing at least one LaTeX paper and one rich-text/OnlyOffice paper.

## Test Data
- Use an existing LaTeX paper for DocumentShell validation.
- Use a rich-text paper to exercise the OnlyOffice adapter.
- Optionally simulate load/error states by temporarily taking the API offline.

## Steps
1. Toggle dark mode, open a LaTeX paper, and confirm the background, status bar, and shell controls respect the theme.
2. Switch to a rich-text paper; verify the surrounding frame and back actions adopt the dark palette.
3. Trigger loading (refresh) to view the spinner panel in dark mode, and note that the messaging remains readable.
4. Force an error (e.g., revoke auth or mock a 500) to confirm the error screen’s buttons and text have dark variants.
5. Return to light mode briefly to ensure no regressions, then back to dark to finish.

## Expected Results
- Loading/error/empty states use slate backgrounds with balanced text contrast.
- DocumentShell and OnlyOffice wrappers inherit the page background without bright flashes.
- Auto-save toast adapts colors based on status but stays legible in dark mode.

## Rollback
- No data changes; revert any temporary API tweaks used to simulate errors.

## Evidence
- Not captured for this run.
