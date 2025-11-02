# Login Redirect Goes To Projects Home

## Purpose
Verify that post-authentication navigation routes users to the Projects landing instead of the removed dashboard route.

## Setup
- Backend API running locally on `http://localhost:8000` with feature flags M0-M3 enabled.
- Frontend dev server running on `http://localhost:3000`.
- Test account exists (e.g., `g202403940@kfupm.edu.sa` / `testpass123`).

## Test Data
- Credentials: `g202403940@kfupm.edu.sa` / `testpass123`.

## Steps
1. Visit `http://localhost:3000/login`.
2. Enter the test credentials and submit the form.
3. Observe the URL and rendered page after authentication.

## Expected Results
- Login request succeeds (HTTP 200) and session token stored.
- Browser navigates to `/`.
- Projects landing page renders with projects list scaffold (no blank screen).

## Rollback
No rollback needed. Logout from the avatar menu if you want to reset the session.

## Evidence
- Manual run; no screenshot captured.
