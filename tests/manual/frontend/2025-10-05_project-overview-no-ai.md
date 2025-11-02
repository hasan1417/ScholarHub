# Purpose
- Confirm the Project Overview page no longer renders the AI Insights panel or quick actions.

# Setup
- Stack running (`docker compose up -d postgres redis onlyoffice backend frontend`).
- Project with existing data (any role with access).

# Test Data
- Project ID accessible to the tester.

# Steps
1. Sign in and navigate to `/projects/<projectId>`.
2. Observe the Overview tab contents.
3. Verify there is no "AI insights" header, quick action buttons, or artifacts list.
4. Confirm the remaining sections show only Project Context and Team Manager cards.

# Expected Results
- AI-related UI is absent from the overview page.
- No console errors while loading.

# Rollback
- Revert the frontend build if AI components need to be restored.

# Evidence
- Screenshot of the Project Overview page showing only Project Context and Team Manager (`tests/manual/_evidence/2025-10-05_project-overview-no-ai.png`).
