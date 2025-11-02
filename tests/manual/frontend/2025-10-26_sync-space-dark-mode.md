## Purpose
Confirm the Sync Space meetings view, including session cards and detail dialogs, renders correctly in dark mode while staying legible in light mode.

## Setup
- Frontend running (Docker or local Vite) with theme toggle accessible.
- Account with a project containing at least one past session and (ideally) a live or scheduled session mock.

## Test Data
- Use existing sync sessions; if unavailable, start a test call to generate a card.
- Ensure at least one session has an attached recording/transcript to exercise the transcript UI.

## Steps
1. Navigate to `Collaborate → Meetings` and toggle the app theme between light/dark while observing the hero header and session list.
2. Inspect a session card in both themes, including status pill, action buttons, transcript preview, and recording link.
3. Open “View transcript” to launch the session modal; review call information and transcript panes in each theme.
4. Expand the inline transcript preview on a session card and verify the scrollable area respects dark mode colors.
5. Trigger the “Clear ended sessions” button (or hover if no sessions) to ensure the control remains visible in dark mode.

## Expected Results
- Hero card, session cards, and empty states adopt slate backgrounds with contrasting borders/text in dark mode.
- Status badges, action buttons, and secondary text stay readable and retain hover states.
- Session modal surfaces (header, detail sections, transcript area) respect dark palettes without losing content contrast.
- Links and chip accents (indigo/emerald) remain vivid but not overpowering on dark backgrounds.

## Rollback
- If you started a throwaway call, end it and remove any unwanted sessions afterward.

## Evidence
- Not captured for this run.
