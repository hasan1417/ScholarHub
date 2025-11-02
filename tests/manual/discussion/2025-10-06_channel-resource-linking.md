# Channel resource linking (papers, related papers, transcripts)

## Purpose
Validate that discussion channels can only link to project papers, approved related papers, and meeting transcripts, and that metadata renders correctly in the sidebar.

## Setup
- Start the dockerized stack (postgres, redis, onlyoffice, backend, frontend).
- Sign in with a project editor or admin.
- Ensure the project has at least one research paper, one approved related paper (project reference), and one meeting with a completed transcript.
- Open the project's Discussion tab and select an active custom channel.

## Test Data
- Project ID with populated paper, approved project reference, and meeting entries.
- User account with permission to manage discussion resources.

## Steps
1. **Open resource drawer**
   - In the selected channel, open the Channel resources panel and press `Link`.
   - Confirm the type selector lists `Project paper`, `Related paper`, and `Transcript` only.
2. **Link a project paper**
   - Choose `Project paper`, select an existing paper from the dropdown, and submit.
   - Verify the paper appears in the list with title, summary snippet, and status/year metadata.
3. **Link a related paper**
   - Press `Link` again, switch to `Related paper`, select an approved project reference, and submit.
   - Confirm the entry shows the reference title, summary, and source/year tags.
4. **Link a meeting transcript**
   - Press `Link`, pick `Transcript`, select a meeting with transcript data, and submit.
   - Ensure the item displays the transcript summary (or generated label) and status badges.
5. **Unlink validation**
   - Remove one of the linked resources using the `x` control and accept the confirmation.
   - Confirm the entry disappears and the counter in the header decrements.
6. **Persistence check**
   - Refresh the page; confirm the remaining linked resources persist with metadata intact.

## Expected Results
- Only supported resource types (paper, related paper, transcript) are available for linking.
- Dropdowns list actual project items with readable titles and context.
- Linked resources render titles, summaries, and contextual tags in the sidebar.
- Unlinking removes the entry without affecting other resources and survives refresh.

## Rollback
- Unlink the test resources after validation or delete the channel to clean up.

## Evidence
- Capture screenshots of each linked resource state and unlink confirmation.
- Store under `tests/manual/_evidence/2025-10-06_channel-resource-linking/`.
