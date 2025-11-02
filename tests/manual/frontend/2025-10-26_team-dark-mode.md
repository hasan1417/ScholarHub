## Purpose
Validate team management surfaces render with the new dark theme styles while remaining legible in light mode.

## Setup
- Frontend stack running (Docker or local Vite) with theme toggle accessible.
- Use an account with access to at least one project containing collaborators.

## Test Data
- Existing project with a few team members.
- Optionally invite a test account you control to verify the modal.

## Steps
1. Sign in and navigate to any project’s overview page; expand the Team section.
2. Toggle the application theme between light and dark, observing the Team list card.
3. Open the “Invite member” modal, inspect fields, helper text, and role cards in both themes, then close the modal.
4. While the modal is open in dark mode, try selecting each role option to ensure focus states remain visible.
5. Back in the list, switch a member’s role (if permitted) and confirm the select + action icons remain legible in dark mode.

## Expected Results
- Team list cards adopt light borders and white cards in light mode, shifting to translucent panels and slate tones in dark mode without contrast loss.
- Invite modal surfaces dark backgrounds, readable labels, and status chips in dark mode while retaining the existing light presentation.
- Role pill chips, status icons, and owner indicators stay color-accessible across themes.
- Inputs and buttons show hover/focus cues in both themes.

## Rollback
- Revert any temporary role changes or invitations issued during the test.

## Evidence
- Not captured for this run.
