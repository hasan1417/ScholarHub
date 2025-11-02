### Purpose
Ensure the “Why lab leads stay with ScholarHub” section reflects the new benefit copy focused on lab operations.

### Setup
- Frontend running locally (`docker compose up -d frontend`).
- Browser in incognito/private mode to avoid cached assets.

### Test Data
- None required; static copy update.

### Steps
1. Visit `http://localhost:3000/` while signed out.
2. Scroll to the trust/benefit band below the hero (title starts “Why lab leads stay with ScholarHub”).
3. Confirm the heading and subheading match the new lab-lead messaging.
4. Verify each card reads “Every decision stays linked”, “No more progress ambiguity”, and “References arrive pre-contextualized” with the updated descriptions.

### Expected Results
- Heading is “Why lab leads stay with ScholarHub”.
- Subheading reads “Keep manuscript pipelines moving without chasing status updates across tools.”
- All three cards display the new titles and descriptions with no layout regressions.

### Rollback
Revert the trust-band copy in `frontend/src/pages/Landing.tsx` and redeploy the frontend.

### Evidence
- Visual confirmation in browser (no capture stored).
