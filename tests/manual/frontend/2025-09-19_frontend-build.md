# Frontend Build

**Purpose**: Confirm the TypeScript cleanup allows `npm run build` to complete successfully.

**Preconditions / Setup**
- Dev mode: Local FE/BE; infra via Docker (optional).
- Working directory: `frontend/`.

**Test Data**
- None.

**Steps**
1) From the project root run `cd frontend`.
2) Execute `npm install` if dependencies are missing.
3) Run `npm run build` and wait for the process to finish.

**Expected Results**
- Step 3: The command exits with status 0 and prints `✓ built` without TypeScript errors.

**Rollback / Cleanup**
- None.

**Evidence**
- `../_evidence/2025-09-19_frontend-build.png`
