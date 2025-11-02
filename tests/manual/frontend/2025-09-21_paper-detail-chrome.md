# Paper Detail Minimal Project Chrome

## Purpose
Confirm the paper detail workspace shows project attribution without exposing the project edit controls or navigation tabs.

## Setup
- Frontend dev server running (`npm run dev`).
- Logged in with access to at least one project that has a paper.

## Test Data
- Existing project `c9116a31-d03d-4896-aa35-c26c59f288c2` with paper `paperId` from the dataset (any paper that loads the detail view).

## Steps
1. Navigate to `/projects/<projectId>/papers/<paperId>`.
2. Observe the top of the page.
3. Inspect the breadcrumb link showing the project name and click it.
4. While on the paper page, ensure no project tab navigation or “Edit project” control is visible.

## Expected Results
- Step 1 loads the paper detail with its overview content populated.
- Step 2 shows only the paper header; the project title appears as a small link without the full project header or tabs.
- Step 3 returns to the project overview when clicked.
- Step 4 confirms the Edit Project button, discovery tabs, and other project-level navigation are absent on the paper page.

## Rollback
None required.

## Evidence
- Verified interactively in browser (no screenshots captured).
