# Channel Artifacts Sunset

## Purpose
Verify that the dedicated channel artifact workflow has been retired and that the discussion sidebar now exposes only resources and tasks alongside the chat experience.

## Setup
- Backend and frontend running from this branch.
- Project with at least one discussion channel that already has a few messages/resources/tasks.
- Logged in as a member with edit access.

## Test Data
- Any existing discussion channel (or create a throwaway one named “artifact-removal-test”).

## Steps
1. Open the project and switch to the **Discussion** tab.
2. Select the target channel and inspect the right sidebar.
   - Confirm only the **Resources** and **Tasks** panels remain; there is no “Channel artifacts” panel or Generate button.
3. In the message composer, type `/artifact Summarize today’s updates` and send.
   - The slash command should no longer trigger a special flow; the assistant treats it like a normal `/` command (falls back to the generic assistant request UI).
4. Open the network inspector and confirm no requests are made to `/discussion/.../artifacts` endpoints when performing the steps above.

## Expected Results
- Sidebar only displays resources and tasks sections; no artifact controls are present.
- Sending `/artifact ...` does not produce a dedicated artifact UI entry; instead it follows the generic assistant workflow.
- No calls to the removed `/discussion/.../artifacts` API endpoints occur.

## Rollback
None required.

## Evidence
- Screenshot of the discussion sidebar showing only Resources/Tasks panels: `tests/manual/_evidence/2025-10-04_channel-artifacts/sidebar.png`
- Console/network capture showing absence of `/artifacts` requests: `tests/manual/_evidence/2025-10-04_channel-artifacts/network.txt`
