# Discovery PDF Indicator Verification

## Purpose
Ensure project discovery results expose open access/PDF availability metadata and render the correct affordances in the manual and active feeds.

## Setup
- Backend API and frontend UI running against the same database with an authenticated user who owns at least one project.
- Feature flag `PROJECT_REFERENCE_SUGGESTIONS_ENABLED` enabled.

## Test Data
- Existing project with discovery preferences configured (keywords/sources populated).
- At least one discovery source capable of returning open access papers (e.g., arXiv).

## Steps
1. Open an eligible project and navigate to the "Discovery" tab.
2. Review the Manual results list; if no historical runs exist, note the empty state message.
3. Enable "Active search feed" and refresh until new auto results populate.
4. For both manual (when available) and active sections, inspect a result with an open access or PDF badge and follow the provided link.
5. Confirm that "View PDF" opens the raw PDF file (content-type `application/pdf`) rather than the abstract/overview page.

## Expected Results
- Manual and active results display a "PDF available" badge when `has_pdf` is true and an "Open access" badge when `is_open_access` is true.
- Clicking "View PDF" opens the actual PDF file in a new tab (content served as `application/pdf`), and "Open link" opens the open-access landing page when no direct PDF is available.
- Cards without a PDF remain unchanged; existing promote/dismiss actions stay functional.
- When no historical manual results exist, the empty state correctly communicates that no manual runs are recorded.

## Rollback
No data rollback required.

## Evidence
- `tests/manual/_evidence/2025-03-07_discovery-pdf-indicators.png`
