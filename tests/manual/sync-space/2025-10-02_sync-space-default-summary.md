# Sync Space default transcript summary

## Purpose
Verify that newly created Sync Space meeting transcripts default to a "Sync Space - <date>" summary when no generated summary is available.

## Setup
- Start the dockerized stack (postgres, redis, onlyoffice, backend, frontend).
- Sign in with a project editor account.
- Navigate to a project that can host a Sync Space session.

## Test Data
- Project with permissions to start Sync Space sessions.
- User account with Sync Space access.

## Steps
1. **Start session**
   - Launch a Sync Space session for the project and allow it to run for at least 1 minute.
2. **End session without AI summary**
   - End the call before the AI/LLM summary finishes (do not manually add a meeting summary).
3. **Inspect meeting record**
   - In the project Meetings view, open the newly created transcript entry.
4. **Link in discussion**
   - In the project Discussion tab, open any channel and press `Link` in Channel resources.
   - Choose `Transcript` and select the new meeting from the dropdown.
5. **Filter validation**
   - Use the `Filter resources` search box to search for part of the meeting name.
   - Clear the filter and note the resources are grouped under `Transcript`, `Project paper`, and `Related paper` headings when available.
6. **Collapse controls**
   - Collapse the Resources, Artifacts, and Tasks panels using the chevron control, then expand them again.
   - Confirm the `Link` or `New task` buttons become available once the panel is expanded.

## Expected Results
- The meeting entry shows a title/summary in the format `Sync Space - YYYY-MM-DD` (using the call date).
- The Channel resources dropdown and linked card display the default title once with no duplicate summary text.
- The linked card shows only the type label `Transcript` under the title (no status chips).
- The filter narrows the grouped lists by title/summary, and clearing it restores all groups with counts.
- In the sidebar list, resource titles are truncated with an ellipsis and no year chips appear in the metadata row.
- Sidebar panels remember their collapsed/expanded state while you stay on the channel, and expanding restores the panel content and actions.

## Rollback
- Delete the test meeting record or unlink it from the channel if not needed.

## Evidence
- Capture a screenshot of the Meetings list showing the default title and the discussion sidebar after linking.
- Store under `tests/manual/_evidence/2025-10-02_sync-space-default-summary/`.
