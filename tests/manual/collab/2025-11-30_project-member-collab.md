Purpose: Verify project members automatically gain paper access for LaTeX collaboration (token, versions, documents).

Setup:
- Backend/DB running with the updated image.
- Two users in the same project: owner of paper `c335ad85-40cb-4c66-b388-b1bd5ae42310` and a project member (not manually added as paper member).
- Paper is LaTeX and assigned to the shared project.

Test Data:
- Project: `7ce05847-1dc3-4ebb-b930-0b093ee63f3e`
- Paper: `AI TEST` (`c335ad85-40cb-4c66-b388-b1bd5ae42310`)
- Project member account: `test@example.com`

Steps:
1) Sign in as the project member (not the paper owner).
2) Open the paper editor at `/projects/7ce05847-1dc3-4ebb-b930-0b093ee63f3e/papers/c335ad85-40cb-4c66-b388-b1bd5ae42310/editor`.
3) Observe network calls for `GET /api/v1/research-papers/{paper_id}` and confirm 200.
4) Trigger collaboration token request (open editor fully) and confirm `POST /api/v1/collab/token?paper_id=...` returns 200 (no 403).
5) Open versions list in the UI; confirm `GET /api/v1/research-papers/{paper_id}/versions` returns 200.
6) Open attached documents list; confirm `GET /api/v1/documents/list?paper_id=...` returns 200.

Expected Results:
- Project member is auto-added as a paper member (role mapped from project role) without manual invites.
- Collab token, versions list, and documents list all succeed with 200 responses.
- Editor content remains visible; no 403 errors in console/network logs.

Rollback:
- Remove the auto-created paper member row if needed: delete the member for `paper_id` and `user_id` in `paper_members` table.

Evidence:
- Screenshots of network panel showing 200 responses for steps 3–6.
