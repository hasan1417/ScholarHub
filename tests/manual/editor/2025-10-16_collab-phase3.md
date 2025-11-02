# LaTeX Collaboration – Manual Test (Phase 3)

**Purpose**
- Validate end-to-end realtime editing between two authenticated users against the Hocuspocus playground.

**Setup**
- Ensure `docker compose up -d redis collab backend frontend` is running.
- Backend env: set `PROJECT_COLLAB_REALTIME_ENABLED=true` and `COLLAB_JWT_SECRET=development-only-secret` (or secure value).
- Frontend env: `VITE_COLLAB_ENABLED=true`, `VITE_COLLAB_WS=ws://localhost:3001`, `VITE_API_BASE_URL=http://localhost:8000`.
- Create or pick a LaTeX-format paper with at least two members (owner + editor).

**Test Data**
- Paper ID shared across two browsers/sessions (e.g., Chrome profile A and Incognito profile B).
- Sample text snippet: `Realtime collaboration verification`.

**Steps**
1. Login as User A, open the LaTeX editor for the target paper.
2. Login as User B in a separate browser/profile and open the same paper.
3. Observe the collaboration badge in the top-right (`Connecting` → `Collaboration active`).
4. User A types the sample text near the top of the document.
5. Confirm User B sees the text within ~1 second and a remote cursor badge.
6. User B deletes the inserted text and adds a different sentence.
7. Confirm User A sees the update instantly and no merge conflicts occur.
8. Trigger a manual compile (or PDF preview) to ensure the shared content flows to the backend without errors.

**Expected Results**
- Collaboration badge shows `Collaboration active` once both sockets connect.
- Both editors see remote cursor highlights with usernames.
- Text edits propagate bi-directionally in real time (sub-second).
- Compile/PDF succeeds against the shared Yjs content (no stale data).

**Rollback**
- Set `PROJECT_COLLAB_REALTIME_ENABLED=false` and `VITE_COLLAB_ENABLED=false` to revert to single-user editing.
- Remove the temporary paper text if needed.

**Evidence**
- Attach screen capture or GIF to `tests/manual/_evidence/2025-10-16_collab-phase3.*` showing both sessions editing simultaneously.
