# ScholarHub Platform Review

## Final Year Project Technical Evaluation

**Date:** February 16, 2026
**Platform:** ScholarHub - Collaborative Academic Research Platform
**Domain:** https://scholarhub.space

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Platform Statistics](#2-platform-statistics)
3. [Discussion AI System Review](#3-discussion-ai-system-review)
4. [LaTeX Editor & AI Features Review](#4-latex-editor--ai-features-review)
5. [Overall Platform Features Review](#5-overall-platform-features-review)
6. [Competitive Analysis](#6-competitive-analysis)
7. [Limitations & Known Issues](#7-limitations--known-issues)
8. [Recommendations](#8-recommendations)

---

## 1. Executive Summary

### Assessment Scores

| Area | Score | Rationale |
|------|-------|-----------|
| Discussion AI System | 8.0 / 10 | Strong architecture with policy-first routing, 28 tools, and multi-model support. Deductions for limited automated test coverage of the policy engine and large file sizes in memory mixin. |
| LaTeX Editor & AI Features | 7.5 / 10 | Full collaborative editing with track changes, SyncTeX, and three export formats. Deductions for the monolithic `ProjectDiscussion.tsx`, lack of frontend unit tests, and incomplete replace handling in track changes. |
| Overall Platform | 8.0 / 10 | Broad feature coverage across 10+ Docker services with production deployment. Deductions for non-functional subscription integration, placeholder landing page content, and absence of user testing data. |

ScholarHub is a full-stack collaborative research platform covering project management, multi-source paper discovery, AI-assisted discussion, LaTeX collaborative editing, video meetings, reference management, and Zotero integration. The codebase totals approximately 102,500 lines across backend (Python/FastAPI) and frontend (React/TypeScript), with 10+ Docker services deployed in production.

The Discussion AI system uses a policy-first architecture: deterministic regex-based routing runs before any LLM call, with the LLM handling only natural language generation. The LaTeX editor combines CodeMirror 6, Y.js/Hocuspocus real-time collaboration, server-side Tectonic compilation with content-hash caching, and SyncTeX bidirectional sync.

### Scope

The platform unifies five phases of the research workflow into one project-scoped environment:

1. **Discover** papers across 8 academic API sources
2. **Collect and analyze** them with AI (PDF ingestion, summarization, cross-paper analysis)
3. **Discuss** findings with an AI assistant using 28 registered tools and multi-model support via OpenRouter
4. **Write** papers collaboratively in LaTeX or rich text with version control
5. **Meet** via integrated Jitsi video calls with Whisper transcription

---

## 2. Platform Statistics

| Metric | Value |
|--------|-------|
| Backend Python LOC | ~53,000 |
| Frontend TS/TSX LOC | ~49,500 |
| Test LOC | ~18,650 |
| Total application code | ~102,500 |
| Database models (tables) | 33 |
| Alembic migrations | 64 |
| API route files | 29 |
| Docker services | 11 |
| AI tools registered | 28 |
| Academic API integrations | 8 |
| Test files | 48 |
| Conference/journal templates | 22 |

### Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React + TypeScript + Vite |
| Backend | FastAPI + Python 3.11 |
| Database | PostgreSQL 15 + pgvector |
| Cache | Redis 7 |
| Collab Server | Hocuspocus (Y.js) for real-time editing |
| Document Editor | OnlyOffice Document Server |
| AI | OpenAI API + OpenRouter (multi-model) |
| Meetings | Jitsi (self-hosted) + Whisper transcription |
| Containerization | Docker Compose (11 services) |
| CI | GitHub Actions (discussion AI quality checks) |

---

## 3. Discussion AI System Review

**Score: 8.0 / 10**

### 3.1 Tool Orchestrator

**File:** `backend/app/services/discussion_ai/tool_orchestrator.py`

Base class coordinating the AI pipeline. Routes messages (lite vs. full), builds LLM context with token-aware windowing, runs the iterative tool-calling loop (up to 8 iterations), applies policy overrides to normalize tool arguments, and extracts structured actions from tool results for the frontend.

- Thread-safe design via `ctx` dict — no shared mutable state between requests
- Policy-forced search fallback: if the policy says "search" but the LLM talks instead, the orchestrator forces a search tool call on iteration 2
- Token-aware context building with budget allocation for system prompt, memory, history, response reserve, and tool output reserve
- `STAGE_HINTS` adapt the system prompt based on the researcher's detected stage
- `HISTORY_REMINDER` injected after conversation history to reinforce key behavioral rules
- Mixin composition (`ToolOrchestrator(MemoryMixin, SearchToolsMixin, LibraryToolsMixin, AnalysisToolsMixin)`)

### 3.2 OpenRouter Orchestrator

**File:** `backend/app/services/discussion_ai/openrouter_orchestrator.py`

Handles multi-model support (GPT, Claude, Gemini, DeepSeek), reasoning parameter negotiation, streaming with tag filtering, retry logic with exponential backoff, model catalog with 3-tier fallback, and recovery retry for missed tool calls.

- **ThinkTagFilter**: Streaming state machine that strips `<think>`, `<thought>`, `<reasoning>`, `<reflection>`, `<function_calls>`, `<invoke>`, `<tool_call>` tags in real-time. Two-layer defense: API `reasoning.effort` parameter + ThinkTagFilter catches anything that leaks through
- **3-tier model catalog fallback**: Remote API (cached 24h in Redis) -> Fallback JSON file -> Hardcoded builtin list
- **Retry with exponential backoff**: Retryable errors (429, 500, 502, 503, 504) get up to 3 attempts with 1s/2s/4s backoff
- **Recovery retry**: If the primary response has no tool calls but the user message contained action verbs, a secondary attempt is made
- **Dynamic context limits**: Context window sizes pulled from the OpenRouter API and pushed into `token_utils`

### 3.3 Policy Engine

**File:** `backend/app/services/discussion_ai/policy.py`

Deterministic, zero-LLM-cost routing layer that runs before any AI call. Routing, year extraction, paper count extraction, and open-access detection are all deterministic regex — the policy enforces the principle that code guarantees behavior while prompts guide language.

- `resolve_search_context` with 5-level priority chain (explicit user topic -> memory hint -> last search topic -> project context -> fallback)
- `is_low_information_query`: Filters queries like "papers about my project" that have no substantive topic content
- `extract_year_bounds`: Handles "last N years", "since YYYY", "from YYYY to YYYY", "between YYYY and YYYY", single year with temporal signal, and generic recency markers
- `extract_requested_paper_count`: Handles digit patterns, word-to-number mapping, and excludes year phrases ("last 3 years" does not become "3 papers")
- Frozen dataclasses (`PolicyDecision`, `SearchPolicy`, `ContextResolution`, `ActionPlan`) enforce immutability
- Deictic marker detection ("this topic", "that area") and relative-only detection ("another 3 papers")
- `ActionPlan.blocked_tools` prevents LLM tool wandering

### 3.4 Intent Classifier

**File:** `backend/app/services/discussion_ai/intent_classifier.py`

LLM-based intent classifier that fires only when the deterministic policy returns "general." Uses a cheap, fast model (gpt-5-mini) with a 2-second hard timeout and 30 max tokens. Layered correctly: deterministic first (free, fast), LLM second (cheap, bounded).

### 3.5 Token Utilities

**File:** `backend/app/services/discussion_ai/token_utils.py`

Token counting with tiktoken, model-aware context limits (dynamic from API + hardcoded fallbacks), budget-based history windowing, and content truncation with sentence boundary awareness.

### 3.6 Route Classifier

**File:** `backend/app/services/discussion_ai/route_classifier.py`

Classifies messages as "lite" (skip tool pipeline) or "full" (run full orchestration). Conservative default to "full." State-based follow-up detection checks `memory_facts._last_tools_called` rather than text heuristics.

### 3.7 Memory Mixin

**File:** `backend/app/services/discussion_ai/mixins/memory_mixin.py` (1,931 lines)

The largest component. Manages a 3-tier memory system:
- **Working memory**: Sliding window of recent messages
- **Session summary**: LLM-compressed older messages
- **Long-term memory**: Preferences, rejected approaches, follow-up items, per-user profiles

Key mechanisms:
- Row-level locking via `SELECT FOR UPDATE` for concurrent memory access
- Research stage tracking with 5 stages (exploring, refining, finding_papers, analyzing, writing) and heuristic detection with inertia
- Per-user memory profiles within channel-level memory
- Clarification loop guardrails that track which "slot" was asked about and how many times
- Contradiction detection via LLM
- Rate-limited fact extraction
- Tool result caching with 5-minute TTL

### 3.8 Search Tools Mixin

**File:** `backend/app/services/discussion_ai/mixins/search_tools_mixin.py`

12 search-related tools including multi-source paper search, batch search, related papers, semantic library search, topic discovery, and project/channel resource retrieval. Multi-source search via `PaperDiscoveryService` (Semantic Scholar, OpenAlex, CORE, CrossRef, PubMed) with library deduplication.

### 3.9 Library Tools Mixin

**File:** `backend/app/services/discussion_ai/mixins/library_tools_mixin.py`

Paper creation (LaTeX with auto-bibliography), paper updates, artifact creation, library management, reference annotation, and project info updates.

Includes fuzzy citation key matching: parses `\cite{authorYYYYword}` keys, extracts author/year/title components, and scores matches against the library. Bridges the gap between LLM-generated citation keys and actual reference metadata.

### 3.10 Analysis Tools Mixin

**File:** `backend/app/services/discussion_ai/mixins/analysis_tools_mixin.py`

Paper focus, cross-paper analysis using RAG with pgvector chunk retrieval, structured paper comparison, research gap suggestion, and discussion-to-LaTeX section generation.

### 3.11 Tool Registry and Permissions

**Files:** `backend/app/services/discussion_ai/tools/`

27 registered tools across 6 modules with role-based access control enforced at both tool filtering (before LLM sees them) and execution time (fail-closed). Two-level enforcement with duplicate tool detection at registration time.

### 3.12 Quality Metrics

**File:** `backend/app/services/discussion_ai/quality_metrics.py`

Thread-safe metrics collection tracking policy compliance: search intent -> tool call rate, clarification-first rate, recency filter compliance, stage transition success. Persists to Redis with time-bucketed history (60s buckets, 30-day retention).

### 3.13 Search Cache

**File:** `backend/app/services/discussion_ai/search_cache.py`

Stores search results in Redis server-side (1h TTL) to prevent prompt injection via crafted paper titles/abstracts.

### Cross-Cutting Discussion AI Scores

| Capability | Score |
|-----------|-------|
| Multi-Model Support | 8.5/10 |
| Tool/Function Calling System | 8.5/10 |
| Memory/Context Management | 8/10 |
| Safety/Policy Guardrails | 8/10 |
| Streaming Support | 7.5/10 |
| Channel-Based Conversations | 7/10 |
| Citation/Reference Integration | 8.5/10 |
| Paper Search Integration | 8/10 |

---

## 4. LaTeX Editor & AI Features Review

**Score: 7.5 / 10**

### 4.1 AI Text Operations

Select text in the editor, choose an AI action from a sparkles menu. "Paraphrase" and "Tone change" replace text in-place. "Summarize", "Explain", and "Synonyms" redirect to the AI chat panel (non-destructive). Five distinct actions, project-scoped model resolution, tone submenu with 5 options.

- Destructive actions are in-place replacements; non-destructive go to chat
- Uses the project's own OpenRouter key and model, not a hardcoded default
- Loading states per-action with visual feedback

### 4.2 Smart Agent (Editor AI Chat)

**File:** `backend/app/services/smart_agent_service_v2_or.py` (1,780 lines)

Agentic AI service powering the editor's AI chat. Can answer questions, propose line-based edits, review documents, convert templates, search references, and ask clarifying questions.

- **Deterministic routing**: `_is_lite_route` skips heavy processing for greetings/acknowledgments
- **Line-based editing**: `propose_edit` tool uses line numbers with anchor text verification
- **Multi-turn tool orchestration**: Can call `search_references` (RAG), receive results, then call `propose_edit`
- **Background rolling summaries**: Long conversations get summarized in a background thread with optimistic locking (`context_version`)
- **Token budgeting**: Uses `fit_messages_in_budget` and `get_context_limit`
- **Retry with backoff**: Retries on transient errors but only before content tokens are sent to client
- **Template conversion**: Two-step process with deterministic converter fallback

### 4.3 Real-time Collaborative Editing (Y.js / Hocuspocus)

Multiple users can edit simultaneously with live cursor positions and selection highlights.

- **Doubled-content detection**: Safety net that detects and fixes Y.Text content accidentally doubled during bootstrap
- **Per-file UndoManagers**: Each file gets its own UndoManager
- **Remote cursors with name labels**: `RemoteCaretWidget` with `computeIdealTextColor` for readability

### 4.4 Track Changes System

**File:** `frontend/src/components/editor/hooks/useTrackChanges.ts`

When enabled (admin-only toggle), insertions are marked with green highlights and deletions shown as strikethrough red text. Changes can be accepted or rejected individually or in bulk.

- Built on Y.js formatting attributes (`trackInsert`, `trackDelete`), surviving reconnections
- Uses `queueMicrotask` to defer `yText.format()` calls, avoiding CodeMirror update cycle crashes (see limitation 7.4)
- Accept/reject operations processed in reverse position order to avoid position shifts

### 4.5 LaTeX Compilation (Tectonic)

**File:** `backend/app/api/v1/latex.py`

Server-side compilation with streaming SSE logs, content-hash-based caching, and automatic BibTeX handling.

- **Content-hash caching**: SHA-256 of source as cache key; same content serves cached PDF instantly
- **BibTeX stabilization**: Checks `.aux` for `\citation`/`\bibdata`, runs bibtex, then up to two more passes with early stop
- **Arabic/RTL auto-detection**: Detects Arabic Unicode ranges, injects fontspec/bidi/Amiri, comments out conflicting packages
- **Unicode escape decoding**: Handles AI models emitting `\u0641` instead of real UTF-8
- **Structured error parsing**: Extracts line numbers from `l.NNN` patterns in logs
- **SyncTeX enabled**: `--synctex` flag passed to tectonic

### 4.6 PDF Preview with SyncTeX

Bidirectional sync between source code and PDF. Forward sync searches +/-10 lines if exact line has no SyncTeX entry. Uses `window.location.origin` instead of `'*'` for postMessage security.

### 4.7 Export Capabilities (PDF, DOCX, ZIP)

Three export formats, each handling multi-file projects, figure directories, and bibliography generation. DOCX export strips XeLaTeX-specific commands for Pandoc compatibility. Source ZIP includes bundled style files.

### 4.8 Version History

**File:** `frontend/src/components/editor/HistoryPanel.tsx` (712 lines)

Shows "Current Changes (Unsaved)" with diff against last snapshot. Server-side diff API. Snapshots grouped by date with human-friendly labels. Types (auto, save, manual, restore) with color-coded badges. Inline label editing. Compilation creates automatic version commits.

### 4.9 Multi-file Support

Additional `.tex` files beyond `main.tex`. Each file maps to a separate Y.Text in the Y.js document. File selector tab bar appears above editor. Compilation sends all extra files to backend.

### 4.10 Document Outline

Side panel showing section hierarchy parsed from LaTeX commands. Handles `\part` through `\subparagraph` with proper nesting. Skips sections inside comments. Binary search for line number resolution. Collapsible tree nodes.

### 4.11 Symbol Palette

Searchable, categorized grid of LaTeX math symbols inserted at cursor.

### 4.12 Citation/Bibliography Integration

Autocomplete for `\cite{...}` commands fetching references from the paper's reference list. `CitationDialog` for detailed interface. BibTeX auto-generated for compilation. Handles multi-cite (`\cite{key1,key2,...}`), caches results per paper.

### 4.13 Auto-compile

Recompiles 4 seconds after last edit when enabled. Uses localStorage for persistence.

### 4.14 Error Diagnostics

LaTeX compilation errors parsed from tectonic logs with line numbers, displayed as inline squiggly underlines via CodeMirror lint system.

### 4.15 Spellcheck

Custom JS-based spellcheck with English dictionary. LaTeX-aware: skips commands, math, comments, bibliography, and reference arguments. Suffix stripping reduces false positives on derived words.

### Architecture Notes

- **Hook decomposition**: Editor split into 12+ focused hooks, each under 300 lines
- **CodeMirror extension system**: Custom extensions for spellcheck, autocomplete, fold service, track changes decorations, and remote selections
- **Backend compilation pipeline**: Streaming SSE + content-hash caching + BibTeX stabilization loop
- **Smart agent's deterministic routing layer**: Clarification detection, operation/target parsing, affirmation rewriting, and lite-route classification happen in code, not prompts

---

## 5. Overall Platform Features Review

### 5.1 Core Features Inventory

| Feature | Depth |
|---------|-------|
| **Authentication** | Email/password, Google OAuth, JWT refresh tokens, email verification, password reset, rate limiting |
| **Project Management** | CRUD, role-based membership (Owner/Admin/Member), email invitations, pending invitations, slug/short-id URLs |
| **Discussion AI** | Multi-model (OpenRouter), 28 tools, tool orchestration, memory/context management, policy engine, quality metrics, intent classification, search caching |
| **Paper Discovery** | 8 academic sources, query building, lexical ranking, deduplication, enrichment, reranking |
| **LaTeX Editor** | CodeMirror, live PDF compilation, autocomplete, spellcheck, SyncTeX, figure upload, symbol palette, multi-file support, track changes, real-time collaboration via Y.js |
| **Rich Text Editor** | OnlyOffice integration with custom plugins for citations and references |
| **Real-time Collaboration** | Hocuspocus + Y.js CRDT, Redis-backed, JWT auth, backend bootstrap |
| **Meetings** | Jitsi integration, recording, transcription (Whisper), AI summaries |
| **References Library** | Personal + project libraries, PDF ingestion, AI-powered suggestions, Zotero import |
| **Embeddings** | SentenceTransformers (local) + OpenAI, pgvector semantic search |
| **Subscriptions** | Tier system (free/pro), usage tracking (see limitation 7.2) |
| **Notifications** | In-app project notifications |
| **Document Versioning** | Snapshots, diffs, branch-based versioning, merge requests |
| **Onboarding** | Welcome modal, feature tour |

### 5.2 Technical Stack Assessment

- **FastAPI + React + TypeScript + PostgreSQL + Redis** — modern, well-suited stack
- **pgvector** for semantic search — avoids separate vector database complexity
- **Y.js/Hocuspocus** for CRDT-based collaboration — industry standard (used by Notion, Figma)
- **Docker Compose** with 11 services — production-grade orchestration
- **OpenRouter** for multi-model AI support — GPT, Claude, Gemini, DeepSeek through one integration

### 5.3 Architecture Assessment

- Clean separation: API routes -> services -> models
- Discussion AI decomposed via tool registry, policy engine, mixins, and quality metrics
- Policy engine enforces principle that routing/validation/guardrails belong in code, not prompts
- Frontend API client with typed endpoints and automatic token refresh with deduplication

### 5.4 Database Design

33 models with normalized schema:
- UUID primary keys throughout
- JSONB for flexible structured data
- pgvector for semantic search
- Cascading deletes
- Check constraints on polymorphic associations
- Unique constraints where appropriate

### 5.5 API Design

29 route files in `/backend/app/api/v1/`. RESTful, consistently structured, with proper HTTP methods. Key routes: auth, projects, project_discussion, project_meetings, project_references, research_papers, discovery, latex, ai, documents, branches, team, users, collab, snapshots, subscription, zotero, metrics, comments, section_locks.

### 5.6 Frontend Assessment

- React Query for server state
- React Router v6 with nested layouts
- Context providers (Auth, Onboarding)
- Custom hooks decomposition in the editor
- TypeScript with 866-line type definitions
- Axios with interceptors for auth token management

### 5.7 Test Coverage

48 test files totaling ~18,650 lines:
- AI memory tests, policy QA sequences, tool permission tests, scope guardrails
- E2E tests for editor AI, discussion AI, tool exposure
- Integration tests for embeddings, template conversion, paper discovery
- Contract tests ensuring API stability
- GitHub Actions workflow (`.github/workflows/discussion-ai-quality.yml`) runs quality checks on push

---

## 6. Competitive Analysis

### 6.1 Feature Comparison Matrix

| Feature | ScholarHub | Overleaf | Notion | Zotero | Semantic Scholar | ResearchRabbit | Elicit |
|---|---|---|---|---|---|---|---|
| **LaTeX Editor** | YES | YES | -- | -- | -- | -- | -- |
| **Rich Text Editor** | YES | -- | YES | -- | -- | -- | -- |
| **LaTeX Compilation + PDF** | YES | YES | -- | -- | -- | -- | -- |
| **Real-time Collaboration** | YES | YES | YES | -- | -- | -- | -- |
| **Version Control (branching)** | YES | Partial | -- | -- | -- | -- | -- |
| **Conference Templates** | 22 | 1000+ | -- | -- | -- | -- | -- |
| **Paper Discovery (multi-source)** | 8 sources | -- | -- | -- | 1 source | 1 source | 1 source |
| **Reference Library** | YES | -- | -- | YES | YES | YES | YES |
| **PDF Ingestion + AI Analysis** | YES | -- | -- | YES (manual) | -- | -- | YES |
| **Zotero Integration** | YES | -- | -- | N/A | -- | -- | -- |
| **AI Research Assistant** | 28 tools | -- | Basic AI | -- | Basic | -- | YES |
| **AI Paper Writing** | YES | -- | YES (generic) | -- | -- | -- | -- |
| **Cross-paper Analysis** | YES | -- | -- | -- | -- | -- | YES |
| **Research Gap Analysis** | YES | -- | -- | -- | -- | -- | Partial |
| **Citation Graph** | -- | -- | -- | -- | YES | YES | -- |
| **Video Meetings** | YES | -- | -- | -- | -- | -- | -- |
| **Audio Transcription** | YES | -- | -- | -- | -- | -- | -- |
| **Team/Project Management** | YES | YES | YES | Groups | -- | Collections | -- |
| **Multi-model AI** | YES (OpenRouter) | -- | 1 model | -- | -- | -- | 1 model |
| **DOCX Export** | YES | -- | YES | -- | -- | -- | -- |
| **Browser Extension** | -- | -- | YES | YES | YES | -- | YES |
| **PDF Annotation** | -- | -- | -- | YES | YES | -- | -- |
| **Data Extraction Tables** | -- | -- | YES | -- | -- | -- | YES |
| **Subscription/Tiers** | Partial | YES | YES | Free | Free | Free | YES |

**Note on comparison scope:** Overleaf, Zotero, and Semantic Scholar are mature products with millions of users and years of development. ScholarHub is a solo-developed Final Year Project. A "YES" in the matrix indicates the feature exists and is functional, not that it matches the polish or scale of commercial equivalents. The comparison is included to show feature coverage breadth and identify gaps.

### 6.2 vs. Overleaf

**ScholarHub covers:** Rich text editor with bidirectional conversion, AI-powered writing assistance, integrated paper discovery and reference management, project-level organization.

**Missing vs. Overleaf:** Direct Git push/pull to external repos (GitHub, GitLab), thousands of templates (vs. 22), mature error recovery, offline support.

### 6.3 vs. Zotero

**ScholarHub covers:** AI analysis of full-text PDFs, semantic search across ingested papers, integrated paper discovery.

**Missing vs. Zotero:** Browser extension for one-click capture, PDF annotation and highlighting, multiple citation style outputs (CSL) beyond BibTeX.

### 6.4 vs. Elicit

**ScholarHub covers:** Full authoring environment, team collaboration, actual paper writing with citations, project management.

**Missing vs. Elicit:** Structured data extraction tables, evidence synthesis with confidence scoring, systematic review protocol support (PRISMA).

### 6.5 vs. Semantic Scholar / ResearchRabbit / Connected Papers

**ScholarHub covers:** Multi-source search (8 sources vs. 1), integrated writing, AI-powered analysis.

**Missing:** Citation graph visualization, timeline visualization, visual exploration interface.

---

## 7. Limitations & Known Issues

### 7.1 Large Single-File Components

`ProjectDiscussion.tsx` is approximately 3,700 lines / 163K characters in a single React component. While the backend uses mixin decomposition effectively (the Discussion AI system splits logic across 6 mixin files), this pattern was not applied consistently on the frontend. The component handles channel management, message rendering, AI streaming, file uploads, and UI state in one file. Extracting this into smaller, focused components would improve maintainability.

### 7.2 Non-Functional Subscription Integration

The subscription system has database models, tier definitions, and usage tracking in place, but the Stripe payment integration is not connected. The `Subscription` model includes Stripe fields (`stripe_customer_id`, `stripe_subscription_id`) that are never populated. Users cannot actually purchase a subscription. This is listed in the features inventory with a caveat for transparency.

### 7.3 Landing Page Placeholder Content

The landing page at `scholarhub.space` displays statistics ("18+ Research Labs", "43% Fewer Revisions") and a testimonial that are placeholder/aspirational content, not based on actual usage data. This should be disclosed proactively in a viva rather than risk being questioned about it.

### 7.4 Track Changes — Incomplete Replace Handling

The track changes transaction filter blocks pure deletions (marking them with `trackDelete` instead of removing text) and handles insertions via the Y.Text observer. However, mixed replace operations (select text + type replacement) are currently blocked entirely — the deletion is marked but the typed replacement character is lost. The code contains a `TODO` comment acknowledging this. This affects a common editing pattern (selecting a word and typing over it).

### 7.5 No Frontend Unit Tests

Backend test coverage includes 48 test files (~18,650 lines), but there are no frontend unit or component tests. React components, custom hooks (particularly the 12+ editor hooks), and utility functions are untested. Libraries like React Testing Library or Vitest could address this.

### 7.6 No User Testing Data

The platform has not undergone formal usability testing with external users. There is no data on task completion rates, user satisfaction, or pain points from real researchers. Even informal testing with 3-5 postgraduate researchers would provide valuable evidence of the platform's practical utility.

### 7.7 No Performance Benchmarks

Response latency for AI queries, LaTeX compilation times, paper search result latency, and collaboration sync latency have not been measured or documented. These would demonstrate engineering maturity and help identify bottlenecks.

### 7.8 Ethical Considerations

The platform uses AI extensively for research assistance, paper writing, and analysis. The following risks are acknowledged but not yet addressed with specific mitigations:

- **AI hallucination in academic context**: The Discussion AI can generate plausible but incorrect claims about papers, methodologies, or findings. No citation verification step exists to cross-check AI-generated statements against source material.
- **Potential for AI-generated plagiarism**: The AI can write LaTeX sections and full paper content. There is no plagiarism detection or originality checking integrated into the platform.
- **Data privacy**: Research data (papers, discussions, drafts) is stored on the server. Data retention policies, export capabilities, and account deletion procedures should be documented.
- **Model provider data exposure**: User content is sent to external AI providers (OpenAI, OpenRouter). Users should be informed about which providers process their data.

### 7.9 Scalability Unknowns

The platform has been tested with a small number of concurrent users. Behavior under load (10+ concurrent editors on one document, 50+ simultaneous AI requests, large reference libraries with 500+ papers) has not been profiled. The Hocuspocus collaboration server and Redis cache are potential bottleneck points.

---

## 8. Recommendations

### 8.1 Top 7 Technical Highlights (For Viva)

1. **Policy-first architecture** — The separation of deterministic routing (`policy.py`, `route_classifier.py`) from LLM behavior enforces the principle that code guarantees behavior while prompts guide language. This is a design pattern that many production AI systems do not implement.

2. **Research stage tracking with inertia** — Detecting where a researcher is in their workflow (5 stages: exploring, refining, finding_papers, analyzing, writing) and adapting AI behavior accordingly. The inertia mechanism prevents rapid stage oscillation.

3. **Two-layer reasoning content filtering** — API-level `reasoning.effort` parameter + streaming ThinkTagFilter state machine. Defense-in-depth for the practical problem that external LLM APIs can leak internal reasoning tokens.

4. **Fuzzy citation key matching** — The `_match_citation_to_paper` scoring algorithm that bridges LLM-generated `\cite{authorYYYYword}` keys to actual reference metadata by extracting and scoring author/year/title components.

5. **Y.js track changes with microtask deferral** — Solves a concurrency issue where synchronous `yText.format()` inside a Y.Text observer crashes CodeMirror during its `view.update()` cycle. The fix defers formatting to `queueMicrotask()`, documented with an explanatory comment in the source.

6. **Quality metrics with time-bucketed history** — Self-monitoring AI system that tracks policy compliance rates (search intent -> tool call rate, clarification-first rate, recency filter compliance) persisted to Redis with 60-second buckets and 30-day retention.

7. **Server-side search cache for prompt injection defense** — Search results cached in Redis server-side (1h TTL) rather than embedded in conversation context, preventing crafted paper titles/abstracts from injecting instructions into the LLM prompt.

### 8.2 Quick Wins (1-2 Hours Each)

1. **Architecture Decision Record (ADR)** — A 2-3 page document explaining: why Y.js for collaboration (vs. OT, Firestore), why policy-in-code for AI routing (vs. prompt-only), why pgvector over a separate vector DB, why OpenRouter for multi-model. Directly supports viva questioning on design rationale. **This is the highest-priority preparation item.**

2. **Unit tests for the policy engine** — `policy.py` is pure, deterministic, and trivially testable. Tests for `extract_year_bounds`, `extract_requested_paper_count`, `is_low_information_query`, and `resolve_search_context` demonstrate software engineering rigor with minimal effort.

3. **Expand CI workflow** — The existing `.github/workflows/discussion-ai-quality.yml` runs quality checks. Extend it to include `pytest` for backend tests and `tsc --noEmit` for frontend type checking. Shows professional practice.

4. **Metrics API endpoint** — `/api/v1/admin/discussion-ai/metrics` returning `snapshot()` and `history()` to expose the existing monitoring capability through the API.

### 8.3 Medium Effort (1-2 Days Each)

5. **Structured Data Extraction Table** — "Extract sample size, methodology, and findings from these 10 papers into a table." The infrastructure (PDF chunks, AI calls) already exists. New tool + frontend table rendering.

6. **Inline AI diff preview** — When Editor AI proposes edits, show green/red diff in the editor that user can accept/reject, instead of text in chat. Uses the existing track changes decoration system.

### 8.4 Larger Effort (2-3 Days)

7. **Citation Graph Visualization** — Use `react-force-graph-2d` + Semantic Scholar citation API. New sub-tab under Library. Visually demonstrates paper relationships.

8. **Decompose ProjectDiscussion.tsx** — Extract channel management, message rendering, AI streaming, and file uploads into separate components/hooks. Addresses the largest known frontend technical debt.

### 8.5 Viva Preparation Notes

- **On the track changes microtask pattern** — Be prepared to explain the CodeMirror update cycle, why synchronous Y.js mutations crash it, and why `queueMicrotask` (not `setTimeout`) is the correct solution. The source comment in `useTrackChanges.ts` lines 168-178 documents this.

- **On the policy engine** — Explain why deterministic routing before LLM calls matters: cost (no LLM call for obvious search queries), reliability (regex doesn't hallucinate routing decisions), and testability (pure functions with known inputs/outputs).

- **On the unified workflow** — A researcher currently needs Semantic Scholar + Zotero + Elicit + Overleaf + Zoom. ScholarHub integrates these into one project-scoped environment where the AI assistant connects all pieces.

- **On the landing page** — If asked about the statistics ("18+ Research Labs"), be upfront that these are placeholder content for the marketing page, not based on actual usage data. The platform itself is functional and deployed.

- **On scope** — ~102,500 lines of application code across 11 Docker services, deployed at `scholarhub.space`. This represents sustained engineering effort over the project period.

---

*Report generated by automated code analysis agents reviewing the full ScholarHub codebase, with revisions based on independent architectural review.*
