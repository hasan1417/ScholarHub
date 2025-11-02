# Purpose
Verify that project invitations require explicit acceptance before access is granted and that the UI surfaces pending invites appropriately.

# Setup
- Project: “AI Literature Review Assistant” with owner `test@example.com`.
- Invitee: `user2@test.com` (registered account, not yet a member).
- Owner logged in in one browser, invitee in another/incognito.

# Steps
1. As the owner, open the project overview and click “Invite member”.
2. Enter `user2@test.com`, assign the `editor` role, submit.
3. Confirm the team list shows the invitee with `Status: invited` and a pending icon; Manage controls should be disabled.
4. Switch to the invitee session and open the dashboard—verify a “Project Invitations” card lists the project with Accept/Decline actions.
5. Attempt to open the project via `/projects` before accepting; should not appear or should return access denied.
6. Click “Accept” on the dashboard card; ensure the project now appears in the projects list and the team entry shows `Status: accepted`.
7. Repeat invite for a second user and choose “Decline”; confirm project remains hidden and team list still shows the member as invited until owner removes them.

# Expected Results
- Pending invites are tracked and blocked from accessing the project until accepted.
- Dashboard shows the new project invitation card, and Remove/Manage actions respect the member’s status.
- Accepting adds the project and grants the expected role; declining prevents access.

# Rollback
- Remove any test members from the project via the team manager after verification.

# Evidence
- `tests/manual/_evidence/2025-09-21_project-invitations.png`
