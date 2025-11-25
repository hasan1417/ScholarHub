# Purpose
Confirm the Project Overview “Project context” card now shows Description, Keyboards, and a numbered Objectives list.

# Setup
1. Ensure the backend API is running (via Docker or local FastAPI env).
2. Start the frontend dev server (`npm run dev`) and open a browser at http://localhost:3000.
3. Sign in with a user that has at least one project containing idea/scope/keywords data.

# Test Data
Use any existing project; ensure its Idea/Scope/Keywords fields are populated so the UI can render real content.

# Steps
1. Navigate to Projects → select a project to reach the Project Overview page.
2. Observe the “Project context” card.
3. Confirm the first section is labeled Description and renders the project idea/scope text.
4. Confirm the second section is labeled Keyboards and renders keyword chips (or the empty-state copy).
5. Confirm the third section is labeled Objectives and renders an ordered (numbered) list derived from the project scope (or the empty-state list item if no scope is set).

# Expected Results
- Description replaces the previous Idea row and shows the project narrative or its empty-state message.
- Keyboards replaces the previous Scope row, showing chips for each keyword or an empty-state message.
- Objectives shows an `<ol>` with numeric bullets; each scope entry (or entire scope string) appears as a separate numbered item, and the empty state still renders inside the ordered list when no objectives exist.

# Rollback
No rollback required; UI-only verification.

# Evidence
- Visual confirmation only (capture to `tests/manual/_evidence/2025-11-12_project-context-objectives.png` if screenshots are collected).
