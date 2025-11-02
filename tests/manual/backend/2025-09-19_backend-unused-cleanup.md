# Backend Unused Services Cleanup

**Purpose**: Ensure the backend no longer contains unused service modules after pruning.

**Preconditions / Setup**
- Repo checkout with the cleanup applied.
- Optional: Python 3.12+ available.

**Test Data**
- None.

**Steps**
1) From project root run:
   ```bash
   python - <<'PY'
   import importlib, pkgutil
   import sys
   sys.path.insert(0, 'backend')
   names = {m.name for m in pkgutil.iter_modules(["backend/app/services"])}
   print('paper_discovery_service_refactored_backup' in names)
   print('reference_ingestion_service' in names)
   print('version_manager' in names)
   PY
   ```
2) Optionally run backend smoke tests `cd backend && python -m compileall app` (or `pytest`) to ensure imports succeed.

**Expected Results**
- Step 1 prints `False` for each removed module.
- Step 2 completes without errors.

**Rollback / Cleanup**
- None.

**Evidence**
- `../_evidence/2025-09-19_backend-unused-cleanup.png`
