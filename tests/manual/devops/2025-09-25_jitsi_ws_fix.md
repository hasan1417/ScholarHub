# Manual Test - Daily Join Stability

## Purpose
Ensure Daily-powered Sync Space calls stay connected for at least 30 seconds and that the token-generated join link does not drop unexpectedly.

## Setup
- Backend running with valid Daily credentials in `.env`.
- Frontend dev server running locally.
- Existing ScholarHub project with Sync Space enabled for the tester.
- Browser DevTools open to monitor console/network warnings.

## Test Data
Use any project where you have editor permissions; no special fixtures required.

## Steps
1. Launch the backend and frontend with Daily credentials configured.
2. Open a project, navigate to **Sync Space**, and click **Start session**.
3. In the live session card, click **Open call window** and join the Daily room.
4. Keep the call tab focused for at least 30 seconds, speaking briefly to ensure audio levels change.
5. Check the browser console for warnings or disconnect messages while the call is active.
6. Return to Sync Space and confirm the session still shows `Live` status after the observation window.

## Expected Results
- Daily room loads immediately and stays connected for the entire observation period.
- Browser console shows no `connection.otherError` or token expiration warnings.
- Sync Space card continues to display the recording banner and `Live` status throughout.

## Rollback
Click **End session** after completing the observation to archive the call.

## Evidence
- Screenshot of the Daily call tab after 30 seconds, saved as `tests/manual/_evidence/2025-09-25_daily_stability.png`.
