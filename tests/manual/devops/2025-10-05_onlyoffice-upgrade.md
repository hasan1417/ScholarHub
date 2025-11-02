# Manual Test: OnlyOffice Document Server Upgrade

## Purpose
Verify that the ScholarHub stack runs successfully against OnlyOffice Document Server 9.0.4 and the editor loads without regressions.

## Setup
- Docker Desktop running.
- ScholarHub repository cloned with updated `docker-compose.yml`.
- `.env` populated with required backend/frontend secrets (no OnlyOffice AI setup needed).
- No local processes using ports 3000, 8000, or 8080 (`lsof -i :8080` to confirm).

## Test Data
- Existing ScholarHub workspace data is sufficient; no special fixtures required.

## Steps
1. Run `docker compose pull onlyoffice` to fetch the 9.0.4 image.
2. Start dependencies: `docker compose up -d postgres redis onlyoffice`.
3. Wait for the `scholarhub-onlyoffice` container to report `healthy` (`docker compose ps onlyoffice`).
4. Navigate to `http://localhost:8080/welcome/` and confirm the editor landing page renders.
5. Open ScholarHub frontend (`docker compose up -d backend frontend`) and log in as a test user.
6. Launch an OnlyOffice document from the ScholarHub UI (e.g., existing paper).
7. Open **Plugins → AI** and manually add the OpenAI provider/models (Name `OpenAI`, URL `https://api.openai.com`, paste key, map Chatbot/Text analysis to `gpt-4o`, Summarization/Translation to `gpt-4o-mini`, Image generation to `dall-e-3`).
8. Inside the editor, open the **About** dialog and confirm the displayed version reads `Document Server 9.0.4`.
9. Sign in with a viewer-only account and open the same document; verify the editor is read-only (OnlyOffice shows “View” mode and controls are disabled).

## Expected Results
- `docker compose pull` completes without errors and lists tag `9.0.4`.
- The OnlyOffice healthcheck (`http://localhost:8080/healthcheck`) returns HTTP 200.
- Editor UI loads inside ScholarHub without console errors.
- AI panel works with the manually configured OpenAI models (Chatbot/Text analysis `gpt-4o`, Summarization/Translation `gpt-4o-mini`, Image generation `dall-e-3`).
- OnlyOffice header is trimmed (no AI/Comment/Publish tabs visible).
 - Viewer role sees the document in read-only mode (no editing allowed, toolbar reflects View state).
- About dialog confirms Document Server version `9.0.4`.

## Rollback
- Revert `docker-compose.yml` to the previous tag (e.g., `git checkout -- docker-compose.yml`) and rerun `docker compose up -d onlyoffice`.

## Evidence
- Capture screenshot of the About dialog showing version 9.0.4 and store at `tests/manual/_evidence/2025-10-05_onlyoffice-upgrade.png`.
