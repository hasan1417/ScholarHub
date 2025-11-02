# Discussion channel AI assistant

## Purpose
Validate that the Scholar AI assistant can answer channel-scoped questions with citations, optional reasoning, and without disturbing existing discussion flows.

## Setup
- Start the dockerized stack (postgres, redis, backend, frontend).
- Sign in with a user who can view project discussions.
- Open a project discussion channel that already has at least one linked resource (paper, reference, or transcript).

## Test Data
- Project with populated discussion threads and linked resources.
- User who can send messages and manage channel resources.

## Steps
1. **Ask a basic question**
   - Scroll to the bottom message composer.
   - Type `/` followed by a question that linked resources can answer and press Enter.
   - Observe that a response card appears above the thread with an answer and citations.
2. **Verify citations**
   - Confirm each citation badge shows the resource title or message label.
   - Click a cited paper/transcript to ensure the resource group in the sidebar is already visible (expand it manually if collapsed).
3. **Reasoning toggle**
   - Enable the reasoning toggle beside the composer and send a slash question.
   - Ensure the response badge indicates reasoning was used and the model name updates.
4. **Empty linked resources**
   - Switch to a channel with no linked resources and ask a question.
   - Confirm the assistant returns guidance to link resources or provide more context.
5. **Suggested actions**
   - When the assistant recommends creating a task, review the summary and accept it.
   - Confirm a task is created with the suggested title/description and the action button marks as completed.
6. **Channel switching**
   - Change to a different channel and verify the assistant history clears.
   - Ask a new question and ensure the new response appears only in that channel.

## Expected Results
- Assistant exchanges render inline in the discussion feed with standard timestamps, model labels, and optional reasoning badge.
- Citations map to existing resources or recent messages; no fabricated references.
- The reasoning toggle reflects the pending state while Scholar AI is working.
- Accepted assistant actions are disabled/marked completed after execution.
- Channels without context produce a guarded answer asking for more information.
- Switching channels resets the assistant composer and history.
- Assistant prose hides raw resource IDs, renders Markdown formatting, and cites sources through chips only.
- Assistant questions/responses stream in-line with the main discussion feed, showing a typing indicator before tokens arrive.
- Assistant replies persist per channel (local storage) and remain after refresh until cleared via the “Clear AI” control.

## Rollback
- No data changes are persisted; simply close the browser tab or navigate away.

## Evidence
- Capture screenshots of a standard answer, a reasoning response, and the no-context message.
- Store under `tests/manual/_evidence/2025-10-03_channel-assistant/`.
- 2025-10-03: Confirmed backend health via `/health` while validating assistant flow (see `tests/manual/_evidence/2025-10-03_channel-assistant/backend_health_check.txt`).
