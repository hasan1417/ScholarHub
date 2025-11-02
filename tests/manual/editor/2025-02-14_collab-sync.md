# LaTeX Collab Sync Regression — 2025-02-14

## Purpose
- Validate that collaborative LaTeX editing pushes updates between multiple browser clients after yCollab initialization tweaks.

## Setup
- Ensure Docker stack is running with `redis`, `collab`, `backend`, and `frontend` services.
- Backend env: `PROJECT_COLLAB_REALTIME_ENABLED=true`, `COLLAB_JWT_SECRET=<shared-secret>`, `COLLAB_WS_URL=ws://collab:3001`.
- Frontend env: `VITE_COLLAB_ENABLED=true`, `VITE_COLLAB_WS=ws://localhost:3001`, `VITE_API_BASE_URL=http://localhost:8000`.
- Two authenticated users with access to the same LaTeX paper (open User A in Chrome, User B in Firefox/Incognito).

## Test Data
- Existing LaTeX paper seeded with minimal content (`\documentclass{article}` skeleton).

## Steps
1. User A opens the paper in the LaTeX editor and confirms the “Collaboration active” badge.
2. User B opens the same paper; wait until their badge also shows “Collaboration active”.
3. User A inserts a unique snippet, e.g. `\section{Realtime Sync Test}` near the top of the document.
4. Observe User B’s editor for the inserted snippet without manual refresh.
5. User B appends `\textbf{Shared edit}` inside the same section.
6. Confirm User A sees the appended text within 2 seconds.
7. Both users move the caret; confirm remote cursor labels appear in the opposite session.

## Expected Results
- Step 3: User B receives the section text automatically, and the collab server logs a document update.
- Step 5/6: User A receives the bold text with no local conflicts or duplicates.
- Step 7: Presence indicators continue to update while editing.

## Rollback
- None required; revert environment variables to disable realtime (`PROJECT_COLLAB_REALTIME_ENABLED=false`, `VITE_COLLAB_ENABLED=false`) if needed.

## Evidence
- Capture a short screen recording or screenshots showing both editors reflecting the same LaTeX content (`tests/manual/_evidence/2025-02-14_collab-sync.*`).
