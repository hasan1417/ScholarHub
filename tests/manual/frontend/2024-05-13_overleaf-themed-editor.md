# Purpose
Verify the LaTeX editor renders with the Overleaf-inspired CodeMirror theme in both light and dark modes and preserves editing focus.

# Setup
- Frontend dev server running via `npm run dev`.
- Browser with access to the ScholarHub frontend (e.g., http://localhost:3000).
- Optional: toggle system/browser dark mode to validate dark styling.

# Test Data
- Existing LaTeX paper or template content with commands, math, comments, and strings.

# Steps
1. Open a paper that uses the LaTeX editor.
2. Observe the editor styling in light mode (commands, comments, strings, math blocks, gutter).
3. Enter dark mode (system toggle or app theme toggle, if available) and revisit the editor.
4. Type within the editor to ensure focus/cursor persist and styles apply during edits.
5. Click Compile and Save to ensure editor interactions remain intact.

# Expected Results
- Light mode shows Overleaf-like colors (blue commands, green comments, red strings, purple math) with updated gutter and selection styling.
- Dark mode swaps to the darker palette while preserving readability and contrast.
- Typing keeps the cursor stable without unexpected focus loss.
- Compile and Save buttons operate normally without disturbing focus.

# Rollback
Revert `frontend/src/components/editor/LaTeXEditor.tsx`, `frontend/src/components/editor/codemirror/overleafTheme.ts`, and theme variables in `frontend/src/styles/index.css` to their previous versions.

# Evidence
- `tests/manual/_evidence/2024-05-13_overleaf-theme_before.png`
- `tests/manual/_evidence/2024-05-13_overleaf-theme_after.png`
