## Purpose
Verify login, registration, and password recovery flows reflect the refreshed UI and copy updates.

## Setup
- Frontend running locally or via docker compose.
- Fresh browser session (private window) to view unsigned pages.

## Test Data
- Use any valid account for login.
- Use a throwaway email such as `ui-test+<timestamp>@example.com` for registration attempts.

## Steps
1. Visit `/login` and confirm the hero card shows the new tagline, field-level errors, and CTA styling.
2. Submit the form with empty fields to ensure validation messaging appears under each input; dismiss errors by correcting the entries.
3. Click “Forgot password?” and confirm the `/forgot-password` route renders, accepts an email, and shows the success banner after the backend call completes (no network errors).
4. Return to `/register`, attempt to submit mismatched passwords, and confirm the inline error surfaces under “Confirm password.”
5. Complete the registration form with valid data to ensure the layout remains responsive and the submit button enters the loading state.

## Expected Results
- Error banners no longer include debug text; field-specific messages appear directly under the relevant inputs.
- “Forgot password?” opens the new recovery screen without 404s.
- Both forms respect reduced spacing on mobile viewports and keep CTAs visible without excessive scrolling.
- Buttons show proper loading feedback while requests are in flight, including the recovery form.

## Rollback
- Remove any test account data created during the registration flow if necessary.

## Evidence
- Not captured for this run.
