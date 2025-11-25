# Purpose
Ensure “Project updated” notifications in the Recent Activity feed use the new Description/Keyboards/Objectives labels instead of idea/scope/keywords.

# Setup
1. Backend API running (Docker stack or local FastAPI env).
2. Frontend dev server via `npm run dev`; sign in at http://localhost:3000 with permissions to edit a project.

# Test Data
- Any existing project. Confirm it already has Description, Keyboards, and Objectives content so edits will trigger all field names.

# Steps
1. Open the project’s Overview page and note the Recent Activity section.
2. Click “Edit project details”, change Description, Keyboards, and Objectives, then save.
3. Observe the new “Project updated” entry at the top of Recent Activity.
4. Confirm the badge text lists “Description, Keyboards, Objectives” (and any other edited fields) with the new wording—no lowercase `idea`, `keywords`, or `scope`.

# Expected Results
- The notification subtitle remains the actor name, but the badge text reflects the remapped labels.
- No legacy field names appear in the card; additional fields (e.g., Title) still show in sentence case.

# Rollback
- Revert any temporary edits to the project if necessary.

# Evidence
- Screenshot the Recent Activity entry after the edit (`tests/manual/_evidence/2025-11-12_project-activity-field-labels.png`) if collecting artifacts.
