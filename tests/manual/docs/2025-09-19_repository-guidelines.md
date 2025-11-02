# Repository Guidelines Doc Check

**Purpose**: Ensure the refreshed `AGENTS.md` contributor guide renders correctly and contains required sections.

**Preconditions / Setup**
- Repo checkout on the feature branch.
- No running services required.

**Test Data**
- None.

**Steps**
1) Open `AGENTS.md` in a Markdown viewer (VS Code preview or `less -R AGENTS.md`).
2) Confirm the document title is "Repository Guidelines" and word count is roughly 200-400 words.
3) Verify the presence of the sections: Project Structure & Module Organization, Build/Test/Development Commands, Coding Style & Naming Conventions, Testing Guidelines, Commit & Pull Request Guidelines, Security & Configuration Tips.

**Expected Results**
- Step 1: Document loads without formatting errors.
- Step 2: Title and overall length match specification.
- Step 3: All section headings appear with concise, repository-specific guidance.

**Rollback / Cleanup**
- None.

**Evidence**
- `../_evidence/2025-09-19_repository-guidelines.png`
