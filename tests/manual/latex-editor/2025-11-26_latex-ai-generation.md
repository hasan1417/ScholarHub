Purpose:
- Verify the LaTeX editor AI assistant can generate a LaTeX body template and draft a section when asked, without adding preambles or Markdown.

Setup:
- Frontend and backend running with latest build.
- Logged in and able to open any LaTeX-mode paper in the editor.

Test Data:
- A LaTeX paper with editable content (can be empty).

Steps:
1) Open a LaTeX paper in the editor and launch AI Assistant (top toolbar).
2) Choose quick prompt “LaTeX Paper Skeleton” and run the prompt with no text selected.
3) Insert the generated output into the document.
4) Highlight a short sentence and select the “Write LaTeX Section” prompt; run it with “Use highlighted LaTeX” enabled.
5) Insert the generated section into the document.

Expected Results:
- Step 2: Streamed reply appears progressively; output uses LaTeX section commands with TODO-style placeholders; no `\\documentclass`, preamble, or Markdown fences.
- Step 3: Inserted text matches the streamed reply and keeps LaTeX commands intact.
- Step 4: Reply uses a `\\section{...}` and a few paragraphs; may include `\\cite{}` placeholders; no preamble or Markdown.
- Step 5: Inserted text respects the selection/insert behavior (replaces selection when highlighted, otherwise inserts).

Rollback:
- Undo the inserted text in the editor or discard changes.

Evidence:
- Screenshot showing the streamed template output and the inserted LaTeX in the editor (`tests/manual/_evidence/2025-11-26_latex-ai-generation.png`).
