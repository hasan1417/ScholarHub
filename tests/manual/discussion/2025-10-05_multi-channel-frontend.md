# Multi-channel discussion frontend UI

## Purpose
Validate the project discussion channel selector and creation workflow in the web UI.

## Setup
- Run the dockerized stack (`docker compose up -d postgres redis onlyoffice backend frontend`).
- Sign in with a project member account that has editor or admin rights.
- Open the project detail page and navigate to the Discussion tab.

## Test Data
- A project that already has baseline messages in the default "General" channel.
- Optional: an additional browser session with a second user to observe real-time updates.

## Steps
1. **Initial landing**
   - Load `/projects/{id}/discussion`; the main area should show a prompt to create the first channel (no chat visible yet).
   - Verify the sidebar is empty except for the `New` button when no custom channels exist.
2. **Create a channel**
   - Press the `New` button above the channel list.
   - In the dialog, enter name "Brainstorm" and description "Ideas for Q4" and submit.
   - Expect the modal to close, the sidebar to show the new channel, and the header to switch to "Brainstorm" with zero threads/messages.
3. **Post message in new channel**
   - Send a text message in the Brainstorm channel; ensure it appears immediately and stats tick to 1 thread/message.
   - Refresh the page to verify the channel selection and message persist.
4. **Switch channels**
   - Click back to the "General" channel; confirm earlier messages load without Brainstorm history.
   - Return to Brainstorm and ensure the new message remains.
5. **Archive toggle**
   - Hover over the Brainstorm entry and use the action menu to archive it.
   - Verify it disappears from the active list (unless include archived) and the page falls back to General.
   - Unarchive the channel and confirm it reappears and can be selected again.
6. **Resources and tasks sidebars**
   - With Brainstorm selected, ensure the resources panel loads (may show empty state if none linked).
   - Link an external resource (paste URL + optional label) and confirm it appears with a remove action; delete it again.
   - Use the "New task" button to create an action item; confirm it appears, cycles status on click, and can be deleted.
7. **Error handling**
   - Attempt to create another channel using the same name; observe error alert from backend (409) and that the modal stays open.
   - Cancel out of the dialog and confirm no duplicate channel appears.

## Expected Results
- Channel selector displays active channel highlighting and statistics per entry.
- New channel creation updates the sidebar, auto-selects the new channel, and clears the form.
- Message posting remains scoped to the selected channel with correct counts.
- Archive/unarchive actions hide and restore the chosen channel appropriately.
- Resource panel supports linking/unlinking entries; tasks drawer supports create/status cycle/delete with immediate updates.
- Duplicate creation surfaced as an error without duplicating entries.

## Rollback
- Delete test messages via API if needed (`DELETE /projects/{project}/discussion/messages/{id}`) or archive the extra channel via backend endpoint.

## Evidence
- Capture screenshots of the channel sidebar before/after creation and the Brainstorm channel message feed.
- Store files under `tests/manual/_evidence/2025-10-05_multi-channel-frontend/`.
