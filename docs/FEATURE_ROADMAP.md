# ScholarHub Feature Roadmap

Expert evaluation conducted 2026-02-16 by three specialized agents (Platform, AI, UX).

**Overall Scholar Suitability Score: 7.5 / 10**

---

## Current Scores

| Dimension | Score | Notes |
|-----------|-------|-------|
| AI Assistance | 9/10 | Strongest differentiator. 28 tools, deterministic policy engine, multi-model, memory system |
| Writing Workflow | 8/10 | LaTeX + rich-text, 21 templates, PDF preview, Arabic/RTL, track changes, collab |
| Literature Management | 7/10 | 8 sources, Zotero import, PDF ingestion with AI analysis |
| Collaboration | 7/10 | Y.js real-time, branching, merge requests, section locks, video meetings |
| Export | 6/10 | PDF, DOCX, Source ZIP. Missing: arXiv format, journal-specific packages |

---

## Priority 1: Must-Have (High Impact)

### 1.1 Replace all `alert()` with toast notifications
- **Effort:** Medium (systematic replacement)
- **Impact:** Fixes the single largest UX problem — 80+ blocking `alert()` calls across the frontend
- **Approach:** Create shared `useToast()` hook + `<ToastContainer />`. The `DocumentShell` already has a local toast pattern — extract and reuse it. Error toasts should include retry actions where applicable.
- **Files:** ~62 files across `src/`

### 1.2 LaTeX autocomplete (commands, environments, citation keys)
- **Effort:** Medium
- **Impact:** Table-stakes for any LaTeX editor. Every researcher expects `\begin{theo` → `\begin{theorem}...\end{theorem}` and `\cite{mcm` completing to `\cite{mcmahan2017communication}`
- **Approach:** CodeMirror 6 has a robust completion API. Citation keys sourced from project reference library via API. LaTeX commands are a static dictionary.

### 1.3 Inline citation suggestion during writing
- **Effort:** Medium
- **Impact:** The feature that makes ScholarHub "write-first" instead of "search-first". No competitor offers this.
- **Approach:** Monitor document edits via Y.js collab server. On paragraph completion, extract key claim, embed via SentenceTransformer, run pgvector similarity search against project library. Return top-3 matches as sidebar suggestions. All infrastructure (embedding service, pgvector, library data) already exists.

### 1.4 Browser extension for one-click save-to-library
- **Effort:** Medium-High
- **Impact:** What makes Zotero indispensable. Without it, adding references requires manual copy-paste.
- **Approach:** Chrome/Firefox extension that detects paper metadata on Google Scholar, PubMed, arXiv, journal pages. Pushes to ScholarHub API. Can leverage Zotero's open-source translator ecosystem.

### 1.5 BibTeX file import/export as first-class operations
- **Effort:** Low
- **Impact:** Researchers switching from Overleaf have existing .bib files with hundreds of entries.
- **Approach:** BibTeX parsing library for Python. Import endpoint parses file, creates Reference records. Export concatenates BibTeX entries from project references.

---

## Priority 2: High Impact, Medium Effort

### 2.1 Structured methodology recommendation engine
- **Effort:** Medium
- **Impact:** "Advisor in a box" — no existing tool does this. Takes user's research question + ingested papers → ranked methodological approaches with citations.
- **Approach:** New `recommend_methodology` tool in analysis_tools module. Pulls methodology fields from all ingested papers (data already extracted by `analyze_reference`). Single tool definition + prompt. All data infrastructure exists.

### 2.2 Research question refinement workflow
- **Effort:** Low
- **Impact:** Addresses the hardest part of research — going from "interested in X" to "specific question Y"
- **Approach:** New `refine_research_question` tool using PICO/SPIDER framework. Takes rough idea + library papers + gap analysis → 3-5 specific research questions with feasibility assessment. Auto-suggested during "exploring" research stage (stage tracking already exists).

### 2.3 Cross-feature navigation links
- **Effort:** Medium
- **Impact:** Connects the siloed tabs. Currently no way to jump from a discovered paper to discussing it, or from a discussion citation to the library.
- **Approach:** Add contextual actions: "Discuss this paper" button on reference cards, "Cite in paper" button that opens editor with citation dialog pre-filled, "View in Library" from discussion citations.

### 2.4 Persist objective completion to backend
- **Effort:** Low
- **Impact:** Currently in localStorage — invisible to collaborators, lost on device change
- **Approach:** PATCH endpoint for objective completion status. Store as `completed_objective_indices: int[]` on project model. Optimistic update with React Query.

### 2.5 LaTeX compilation validation for AI-generated content
- **Effort:** Very Low (~50 lines)
- **Impact:** Catches 80% of LaTeX errors before user sees them. Every researcher using AI for LaTeX has experienced compilation failures.
- **Approach:** After `create_paper` or `update_paper` tool execution, run regex-based syntax check (unmatched braces, unclosed environments, missing `$`, unescaped `%`/`&`/`#`). Include errors in tool result so LLM self-corrects.

---

## Priority 3: Nice-to-Have

### 3.1 Writing quality analyzer for academic prose
- **Effort:** Medium
- **Impact:** No competitor offers research-specific writing analysis tied to submission venue
- **Approach:** Citation density check (flag paragraphs with claims but no citations), hedging analysis, structure analysis (Introduction follows context-gap-contribution), venue conformance (abstract word limits, section naming). Steps 1-3 can be deterministic. Template infrastructure already exists (21 templates).

### 3.2 Command palette / quick navigation (Cmd+K)
- **Effort:** Medium
- **Impact:** Power-user feature. Researchers navigate many projects/papers.
- **Approach:** Cmd+K dialog searching across projects (by title/keyword), recent papers, common actions. Uses existing React Query cached data.

### 3.3 PDF annotation and highlighting
- **Effort:** High
- **Impact:** Every reference manager offers this, but AI analysis partially compensates
- **Approach:** pdf.js with annotation layer. Annotations stored server-side, linkable from AI discussion.

### 3.4 Citation graph visualization
- **Effort:** Medium
- **Impact:** ResearchRabbit's core feature. Semantic Scholar and OpenAlex APIs already connected.
- **Approach:** D3 force-directed graph or react-force-graph. AI tools (`suggest_research_gaps`, `analyze_across_papers`) feed into visualization.

### 3.5 Rename "Scholar AI" tab to match actual functionality
- **Effort:** Low (label change) to Medium (restructure default view)
- **Impact:** Current label creates expectation mismatch — it's a full discussion system with AI, not a pure AI chat
- **Options:** "Discussion" or "Team & AI". If leading with AI, restructure so AI chat is default view with team channels secondary.

### 3.6 Consolidate global Discovery Hub with per-project Library
- **Effort:** Low
- **Impact:** Having `/discovery` as global and `/projects/:id/library/discover` as project-scoped creates confusion
- **Approach:** Remove global Discovery Hub route. Discovery always in project context. Add "Quick Search" (Cmd+K style) for project-independent search.

### 3.7 Improve mobile experience for non-editor pages
- **Effort:** Medium
- **Impact:** Researchers check project status and discussions on mobile
- **Approach:** Show tab labels on mobile (not just icons), editor shows "View only" mode rendering PDF without CodeMirror.

### 3.8 Submission package builder
- **Effort:** Medium
- **Impact:** Saves hours per journal submission
- **Approach:** Template-driven configuration. Conference requirements encoded as JSON rules. Source ZIP already exists — extend with venue-specific folder structures.

### 3.9 Proactive AI (biggest architectural gap)
- **Effort:** High
- **Impact:** Currently AI is entirely reactive. Never says "I notice you have 10 papers on X but none on Y — should I search?"
- **Approach:** Act on research stage transitions (memory system already tracks stages). Trigger suggestions when: new papers added without citation, library gaps detected, stage changes from exploring to refining.

---

## Competitive Advantages (Already Implemented)

**vs. Overleaf:** Paper discovery (8 sources), AI assistant (28 tools), video meetings, automated reference ingestion, multi-model AI

**vs. Zotero/Mendeley:** Integrated discovery-to-citation workflow, AI literature reviews, collaborative project workspace

**vs. Elicit/Semantic Scholar AI:** Full workflow (search → manage → analyze → write), project-scoped persistent memory

**vs. ResearchRabbit:** Writing and collaboration layer, AI acts on discovered papers, per-project auto-refresh feeds
