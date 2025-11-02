# Purpose
Validate the reverted paper detail layout renders the basic gray/white theme while keeping project-sourced team members, references, and document actions functional.

# Setup
- Shared docker compose stack already running (`backend`, `frontend`, and infra services).
- Sign in with an account that can access at least one project + paper with documents and references attached.

# Test Data
- Project with a known paper (e.g. `Project Alpha`).
- Paper containing at least one uploaded document and approved project reference.

# Steps
1. Navigate to `/projects/<projectId>/papers/<paperId>`.
2. Confirm the header uses the neutral gray/white styling (no gradients) and shows status/type badges with indigo primary accents.
3. Toggle `Edit` and verify inline controls (title, status, visibility) update then cancel to discard changes.
4. Verify the vertical `Attached references` list beneath keywords, detach a reference (if authorized) and reattach it through `Manage` to confirm the list refreshes.
5. Check the `Team` card lists project members without paper-level invite actions.

# Expected Results
- Page matches the basic design with indigo primary buttons and no gradient accent styling.
- Edit mode reuses the inline form fields and cancelling restores original text.
- Vertical reference cards show summaries, open DOI/links, and detach/reattach operations update immediately as permissions allow.
- Team list mirrors the project roster with read-only display.

# Rollback
No special rollback required; UI change only.

# Evidence
No screenshots captured.
