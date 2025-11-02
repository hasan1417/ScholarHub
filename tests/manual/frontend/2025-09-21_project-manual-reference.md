# Purpose
Verify project owners and editors can manually add a related paper with optional PDF from the Related Papers tab.

# Setup
- Project with at least one owner (Hassan) and one editor account.
- Log in as the owner or editor.
- Ensure discovery feature flag remains enabled.

# Test Data
Title: "Manual Reference Smoke"
Authors: "Jane Doe, John Smith"
Year: 2024
DOI: 10.1234/manual.smoke
Journal: Manual QA Journal
PDF: `fixtures/sample.pdf` (any small PDF file)

# Steps
1. Navigate to the project overview and open the Related Papers tab.
2. Click the new “Add related paper” button in the header.
3. Complete the modal using the data above and attach the PDF.
4. Submit the form and wait for the modal to close.
5. Confirm the new reference appears in the list with the entered metadata.
6. Download or inspect the entry to ensure the PDF link is present.
7. Sign in as a viewer to confirm the Add related paper option is hidden.

# Expected Results
- Owners and editors see the Add related paper button; viewers do not.
- Submitting the modal adds the reference to Related Papers immediately without needing to visit Discovery.
- PDF uploads succeed and are accessible from the reference entry.

# Rollback
- Optionally remove the test reference via admin tools or backend script if not needed.
- Delete uploaded PDF if required for cleanliness.

# Evidence
- `tests/manual/_evidence/2025-09-21_project-manual-reference.png`
