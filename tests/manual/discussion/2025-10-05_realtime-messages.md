# Purpose
- Confirm discussion channel messages appear in real time across multiple users without manual refresh.

# Setup
- Run the stack (`docker compose up -d postgres redis onlyoffice backend frontend`).
- Two browser profiles or devices with different project members (e.g., Admin and Viewer/Editor).
- Project with at least one discussion channel.

# Test Data
- Project ID and discussion channel ID/slug accessible by both users.

# Steps
1. Sign in as User A and open `/projects/<projectId>/discussion` selecting the target channel.
2. Sign in as User B in another window and open the same channel.
3. With both views visible, send a new top-level message from User A.
4. Observe User B's screen without refreshing.
5. Reply to the new message from User B and watch User A's view.
6. Edit the reply from either user and verify the other screen updates.
7. Delete the reply (as the author/admin) and ensure the deletion banner shows on both screens immediately.
8. From User A, ask the AI assistant a question in the channel sidebar.
9. Confirm User B sees the assistant response appear without refreshing.

# Expected Results
- Messages, edits, and deletions appear on the other user's screen within ~1 second without manual reload.
- The discussion sidebar counts remain accurate after each action.
- No WebSocket errors appear in the browser console.
- AI assistant exchanges are visible to all channel participants in real time.

# Rollback
- None; no persistent changes required beyond posted discussion messages.

# Evidence
- Screen recording or animated GIF showing both users with instantaneous updates (`tests/manual/_evidence/2025-10-05_realtime-messages.mp4`).
