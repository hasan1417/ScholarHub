# Project References Card Header Spec

## Layout
- **Left section**: reference title, year/source badges, authors, journal.
- **Right section**: upload button or status pill, followed by the Delete icon, aligned flush right with 12–16 px spacing.

## PDF call-to-action
- When no PDF is stored, show a pill-shaped button labeled `Upload PDF` (uppercase microcopy) that opens the file picker; the button shows `Uploading…` while in progress.
- When a PDF is already stored/processed, show a muted pill `PDF on file` to confirm availability; viewing remains via the Source link below the card.

## Secondary icon
- `Delete`: circular destructive icon button (36×36 px) on the far right with tooltip `Delete`; opens the confirmation modal and backs the Undo toast.

## Delete flow
1. Press Delete → modal `Delete this item?` (Cancel default focus, Delete in red with loading state).
2. On success, invalidate the list and surface the Undo toast for 6.5 s; undo recreates the suggestion by re-approving it.

## Accessibility
- Upload button/ Delete icon expose descriptive `aria` labels and remain ≥36 px for touch.
- Focus outlines meet WCAG 2.1 AA; status pill text contrasts at ≥3:1.
- Keyboard order: title → badges → Upload PDF / PDF on file → Delete.
