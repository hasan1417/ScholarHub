# Purpose
Verify that the new Admin, Editor, and Viewer roles enforce the intended permissions for project collaboration, reference management, and paper editing.

# Setup
- Backend and frontend running locally against the same database.
- Three test users created: Alice (project owner/admin), Bob (editor invitee), Carol (viewer invitee).
- A project with one paper exists; Bob invited as editor and Carol as viewer via the updated invite modal.

# Test Data
| User  | Role   | Credentials |
|-------|--------|-------------|
| Alice | Admin (owner) | alice@example.com / ******** |
| Bob   | Editor | bob@example.com / ******** |
| Carol | Viewer | carol@example.com / ******** |

# Steps
1. Sign in as Alice and open the paper detail page.
2. Confirm the team invite button is visible and send an additional invite (smoke) to ensure Admin can manage team members.
3. Click the team header “Manage” button, use the role selector to downgrade Bob temporarily to `viewer`, then restore him to `editor`.
4. Remove a non-critical member (e.g., a test invitee), then re-invite them to confirm the owner can manage membership.
5. Attach and detach a project reference from the References panel.
6. Open the editor from the detail page to confirm edit access, then return.
7. Sign out and sign in as Bob; open the same paper detail page.
8. Verify Bob cannot see the invite button, can open the editor, and can approve or detach project references.
9. Sign out and sign in as Carol; open the same paper detail page.
10. Confirm Carol cannot see invite or reference management actions, and the Open Editor button is hidden. Attempting to visit the editor URL directly should show a permission alert.

# Expected Results
- Alice can invite teammates, manage references, and reach the editor.
- Bob can be downgraded to viewer and restored by an admin, can manage references and edit content while in editor role, but cannot invite or delete the paper.
- Carol sees read-only UI with no ability to edit, attach/detach references, or invite members, and client shows a permission warning if she tries to open the editor directly.

# Rollback
- Remove the test invitations from the team management panel and delete any temporary references created during the test.
- Sign the test users out.

# Evidence
- `tests/manual/_evidence/2025-09-21_team-role-permissions.png` – Screenshot of Carol’s read-only view with disabled actions.
