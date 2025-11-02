# Purpose
Ensure the LaTeX editor split mode displays both panes at a fixed width and no longer exposes a resizable divider.

# Setup
- Frontend dev server running via `npm run dev`.
- Browser pointed at http://localhost:3000 with a LaTeX-capable paper opened.

# Test Data
- Any paper containing compile-able LaTeX content.

# Steps
1. Switch the toolbar view mode to `Split`.
2. Hover between the editor and preview panes and attempt to drag any divider.
3. Toggle between `Editor`, `Split`, and `Preview` modes and return to `Split`.
4. Resize the browser window wider and narrower while in `Split` mode.

# Expected Results
- Split mode shows the editor and preview panes simultaneously at an even (roughly 50/50) width.
- No resize cursor or draggable separator appears between the panes, and dragging attempts have no effect.
- Switching modes does not alter the fixed split proportions once returning to `Split`.
- Browser window resizing keeps the panes proportional without exposing a drag handle.

# Rollback
Revert changes to `frontend/src/layout/SplitShell.tsx` and `frontend/src/state/uiStore.ts`.

# Evidence
- `tests/manual/_evidence/2024-05-13_split-mode-fixed.png`
