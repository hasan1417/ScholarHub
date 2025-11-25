# Purpose
Verify the project creation/edit modal now collects Description, Keyboards, and Objectives in the updated format.

# Setup
1. Backend API running (Docker stack or local FastAPI).
2. Frontend dev server running via `npm run dev`; browse to http://localhost:3000 and sign in with a user who can create/edit projects.

# Test Data
- Use an existing project for edit validation.
- Sample data:
  - Description: “Exploring microfluidic cooling for dense neural nets.”
  - Keyboards: `microfluidics, thermal, ai hardware`
  - Objectives (one sentence per row in the list):
    1. Benchmark thermal droop under various loads.
    2. Document fabrication constraints.
    3. Identify partner labs for prototyping.

# Steps
1. From Projects Home, click “Create a project”.
2. Confirm the modal shows Title, Description (textarea), Keyboards (comma-separated input), and an Objectives list with numbered sentence inputs plus an “Add objective” button.
3. Use “Add objective” to create three rows; enter the sample sentences and confirm each can be removed individually (except the last).
4. Fill in Description/Keyboards and click “Create project”; verify submission succeeds (or fails only for unrelated reasons).
5. For editing, open any project → “Edit” and confirm the objectives list is pre-filled with one sentence per row; adjust a sentence and save.

# Expected Results
- Modal labels and helper copy reference Description, Keyboards, and Objectives (no Idea/Scope remnants).
- Keyboards input accepts comma-separated values and helper text mentions keyboards explicitly.
- Objectives list enforces numbered, sentence-level rows with add/remove controls; entries persist after saving.
- Project Overview reflects the updated Description and numbered Objectives immediately after create/edit.

# Rollback
If created a throwaway project for the test, delete it via the Projects page; revert any temporary edits.

# Evidence
- Capture the updated modal (creation + edit) into `tests/manual/_evidence/2025-11-12_project-form-description-keyboards.png` if screenshots are taken.
