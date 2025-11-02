# Purpose
Verify the LaTeX editor keeps the CodeMirror instance stable, avoids React re-renders while typing, and no longer exposes auto-compile.

# Setup
- Frontend dev server running via `npm run dev`.
- Browser connected to http://localhost:3000 with a LaTeX document open.
- React DevTools Profiler available in the browser.

# Test Data
- Any LaTeX document with mixed content (text, math, citations).

# Steps
1. Open the React DevTools Profiler and start recording.
2. Type continuously in the LaTeX editor for 10+ seconds without pausing.
3. Stop recording and inspect the profiler flamegraph to confirm `LaTeXEditor` shows 0 renders during typing.
4. Trigger a pause in typing and wait ~300ms to observe a single render from buffered propagation.
5. Confirm the Compile and Save buttons remain responsive and preserve focus; ensure no auto-compile toggle is visible.

# Expected Results
- While typing, the profiler shows 0 renders for `LaTeXEditor`; a single render occurs only after typing stops.
- The editor retains focus throughout; no blur/flicker occurs.
- Compile and Save operate on the latest buffer without reintroducing auto-compile UI.

# Rollback
Revert `frontend/src/components/editor/LaTeXEditor.tsx`, `frontend/src/layout/SplitShell.tsx`, and `tests/manual/frontend/2024-05-13_overleaf-themed-editor.md` to their previous versions.

# Evidence
- `tests/manual/_evidence/2024-05-13_latex-editor-uncontrolled.png`
