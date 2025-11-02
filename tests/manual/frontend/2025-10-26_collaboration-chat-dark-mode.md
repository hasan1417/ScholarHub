## Purpose
Verify the collaboration chat view, including channel sidebar, message area, and resource/task dialogs, render with the new dark theme styling.

## Setup
- Frontend running (Docker or local Vite).
- Account with access to a project that has at least one chat channel and sample messages/resources.
- Enable the theme toggle in the UI.

## Test Data
- Existing project discussion channel with a mix of human + AI messages.
- At least one linked resource and task to exercise the dialogs.

## Steps
1. Log in, open a project, and navigate to `Collaborate → Chat`.
2. Toggle the application theme between light and dark, observing the main chat header, message list, and sidebar.
3. Open the “Channel resources” dialog, scroll through available items, filter, and close the dialog.
4. Open the “Channel tasks” dialog, toggle the create form, and inspect task list items in both themes.
5. Enter a quick message (or edit an existing one) to confirm the composer/input reflects the dark theme and remains legible.

## Expected Results
- Sidebar, header, and message cards adopt slate-toned surfaces in dark mode without losing contrast.
- Resource/task dialogs inherit dark backgrounds, with inputs, tabs, and chips remaining readable.
- Message bubbles and AI response cards switch to darker backgrounds while keeping accent colors and hover states.
- Composer textarea, reply/edit bars, and action buttons show appropriate dark hover/focus cues.

## Rollback
- Delete any placeholder messages or tasks created during the test if they’re not needed.

## Evidence
- Not captured for this run.
