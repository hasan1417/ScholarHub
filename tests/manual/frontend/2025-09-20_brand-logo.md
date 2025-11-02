# Navbar Branding Text

## Purpose
Validate that the ScholarHub wordmark renders in the layout header without breaking navigation or theme controls.

## Setup
- Frontend dev server running at `http://localhost:3000`.

## Test Data
- Logged-in user session (any account).

## Steps
1. Log in and land on the Projects home page.
2. Inspect the header: confirm the word "ScholarHub" appears in the navbar as the clickable brand link.
3. Click the brand link; ensure it routes to `/projects`.
4. Toggle the theme via settings and verify the wordmark remains visible in both modes.

## Expected Results
- Text label displays with the same typography as before (bold, legible), and the navigation continues to function.
- Clicking the logo returns to Projects home.
- Theme switching does not affect the logo’s visibility.

## Rollback
Not applicable (this is the baseline text treatment).

## Evidence
- Manual verification; no screenshot captured.
