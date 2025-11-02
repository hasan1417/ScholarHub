# Manual Test – Related paper analysis status sync

**Purpose**
- Confirm references with processed PDFs automatically show `Analysis: analyzed` in the related papers list.

**Setup**
- Backend/Frontend containers rebuilt from current branch (`docker compose up -d --build backend frontend`).
- User signed in with project ID `7ce05847-1dc3-4ebb-b930-0b093ee63f3e`.

**Test Data**
- Reference `Risk Alignment in Agentic AI Systems` (id: `a84faa8d-5197-443d-b1df-1537f95f61bb`) already has an ingested PDF (`document_id=6a095898-0188-4fd0-885d-16b4a310d386`).

**Steps**
1. Load `/projects/7ce05847-1dc3-4ebb-b930-0b093ee63f3e/references?status=approved` in the browser.
2. Refresh once to trigger the new sync logic.
3. Observe the status badge for `Risk Alignment in Agentic AI Systems`.

**Expected Results**
- Badge reads `Analysis: analyzed` (emerald tone) and no `Upload PDF` CTA is shown.

**Rollback**
- None required.

**Evidence**
- `python` snippet executed inside backend container:
  ```
  docker compose exec backend bash -lc "python - <<'PY'
  from app.database import SessionLocal
  from app.models import Reference
  ref_id = 'a84faa8d-5197-443d-b1df-1537f95f61bb'
  session = SessionLocal()
  ref = session.query(Reference).filter(Reference.id == ref_id).first()
  print(ref.status)
  session.close()
  PY"
  ```
  Output: `analyzed`
