# Project‑First Workflow Migration

Status: Draft
Owner: Platform Team (Backend + Frontend)
Last updated: 2025-09-20

## Scope

- Shift product from paper‑first to project‑first while preserving existing papers.
- Introduce collaboration at both project and paper levels (memberships, invites, comments, presence, activity).
- Add scoped AI at project and paper levels (chat, summaries, literature review, outline/directory help, right‑click intents).
- Build reference intelligence flows (suggest → approve/reject → attach to papers).
- Add meetings/speech pipeline (upload audio → transcribe → MoM/action items → seed paper creation).
- Notifications feeds (project updates, AI job completions, comments/mentions).
- Frontend routing revamp and minimal navbar (Projects, Profile, Settings). Landing page is Projects Home with create + list of all projects.

Out of scope (explicitly excluded): subscriptions, market survey, storage/quota management. LaTeX editor theming/stability/split‑view work is already completed.

## Milestones (M0–M8)

- M0: Preparation & feature flags
- M1: Data model & DB migrations
- M2: Backend APIs (projects, papers, references, AI, meetings, notifications)
- M3: Frontend routing + Projects Home + icon navbar
- M4: AI scoping + reference suggestions/approval flows
- M5: Collaboration (members, invites, comments, presence, activity)
- M6: Meetings/speech + notifications UI
- M7: Cutover (redirect legacy routes) + deprecations
- M8: Hardening (tests, docs, manual tests) & rollout

## Acceptance (global)

- After login, users land on `/projects`, can create a project and view all accessible projects.
- Projects own papers; every legacy paper is mapped to a project.
- AI chats and tools are limited by scope (project vs paper context differs as defined below).
- Collaboration works at both levels with enforced RBAC.
- New routes available with OpenAPI; legacy routes redirect with deprecation notices.

## Database & Migrations (Alembic)

New/updated tables and fields. Apply in discrete revisions for safe rollout and rollback.

1) R1 — Projects and Membership

- `projects` (id PK, title, idea TEXT, keywords JSONB, scope TEXT NULL, status TEXT, created_by FK users, created_at, updated_at)
- `project_members` (project_id FK, user_id FK, role ENUM('owner','editor','viewer'), created_at, updated_at, UNIQUE(project_id, user_id))

2) R2 — Papers linkage & metadata

- Alter `papers`: add `project_id` (FK projects, NULL initially), `format` ENUM('latex','rtf') NULL, `summary` TEXT NULL, `status` TEXT NULL

3) R3 — References linking

- `project_references` (project_id FK, reference_id FK, status ENUM('pending','approved','rejected'), confidence NUMERIC NULL, decided_by FK users NULL, decided_at TIMESTAMP NULL, created_at, updated_at, UNIQUE(project_id, reference_id))
- `paper_references` (paper_id FK, reference_id FK, created_at, UNIQUE(paper_id, reference_id))

4) R4 — Collaboration primitives

- `paper_members` (paper_id FK, user_id FK, role ENUM('owner','author','reviewer','viewer'), created_at, updated_at, UNIQUE(paper_id, user_id))
- `invites` (id PK, target_type ENUM('project','paper'), target_id, email, role TEXT, status ENUM('pending','accepted','revoked'), token, expires_at, created_at, updated_at)
- `comments` (id PK, target_type ENUM('project','paper'), target_id, author_id FK users, body TEXT, anchors JSONB, resolved BOOLEAN DEFAULT false, created_at, updated_at)
- `activities` (id PK, target_type ENUM('project','paper'), target_id, actor_id FK users, type TEXT, payload JSONB, created_at)

5) R5 — AI artifacts, meetings, notifications

- `ai_artifacts` (id PK, target_type ENUM('project','paper'), target_id, type ENUM('summary','litReview','outline','directoryHelp','intent'), payload JSONB, status ENUM('queued','running','succeeded','failed'), created_at, updated_at)
- `meetings` (id PK, project_id FK, audio_url TEXT, transcript JSONB NULL, summary TEXT NULL, action_items JSONB NULL, created_at, updated_at)
- `notifications` (id PK, project_id FK, type TEXT, payload JSONB, read BOOLEAN DEFAULT false, created_at)

6) R6 — Backfill & finalize constraints

- Populate `papers.project_id` (see Backfill Plan). Then set `NOT NULL` and add index.
- Add helpful indexes (GIN on `projects.keywords`, composites on membership/link tables).

## Data Backfill Plan

Strategy: move ALL existing papers into a single Dummy Project per tenant/team. Safe, idempotent, and reversible. This creates a clean starting point that users can later reorganize into multiple projects.

- Create one Dummy Project named "Legacy Migration" (configurable via flag `--dummy-project-name`).
- Assign ownership to the tenant/team owner (or a designated system user), and add paper owners as project members (role `editor`).
- For each paper: set `project_id` to the Dummy Project.
- Paper authors → `paper_members` (owner → owner; collaborators → author).
- For each `paper`→`reference` link (if present): insert into `project_references` with status `approved` (project = Dummy Project).
- Script: `backend/app/scripts/migrate_to_projects.py`
  - Modes: `--dry-run`, `--execute`, `--mode dummy`, `--dummy-project-name "Legacy Migration"`
  - Optional override to previous behavior: `--mode cluster` (per-owner or per-team) if privacy requires separation.
  - Outputs CSV/JSON mapping paper→project for audit/rollback.
- After verification: apply R6 to enforce `NOT NULL` on `papers.project_id`.

UX note: On first visit to `/projects`, show a dismissible banner on the Dummy Project prompting owners to split papers into proper projects.

Rollback bookmarks: persist mapping for reversal; keep legacy routes active until M7.

## Backend APIs (FastAPI)

New/updated routes. All routes documented in OpenAPI and guarded by RBAC.

- Projects (`backend/app/api/routes/projects.py`)
  - CRUD: list/read/create/update/delete
  - Members: list/add/change role/remove
  - Update idea/keywords/scope
  - Updates feed (notifications list)

- Papers (`backend/app/api/routes/papers.py`)
  - Nested: `/projects/{project_id}/papers`
  - CRUD; create from discussion summary; status transitions
  - Summarize endpoint; literature review generation from selected references
  - Members: list/add/change role/remove

- References (`backend/app/api/routes/references.py`)
  - Search; project suggestion queue; approve/reject; attach/detach to papers

- AI (`backend/app/api/routes/ai.py`)
  - Scoped chat sessions (target=project|paper)
  - Jobs: summarize, litReview, outline/directoryHelp, right‑click intents

- Meetings (`backend/app/api/routes/meetings.py`)
  - Upload audio; job status; fetch transcript, MoM, action items

- Notifications (`backend/app/api/routes/notifications.py`)
  - List, filter, mark‑read

- Realtime (`backend/app/core/realtime.py`)
  - Channels: `project:{id}`, `paper:{id}` for presence, cursors/typing, comments

- RBAC middleware
  - Enforce roles from `project_members`/`paper_members`; permission matrix documented in tags.

## AI Scoping & Jobs

- Context builder (`backend/app/services/ai/context.py`)
  - Project context = idea + keywords + approved project references
  - Paper context = project context + paper references + current paper content
  - Deterministic selection caps (relevance + recency)

- Jobs (`backend/app/services/ai/jobs.py`)
  - Summarize paper, generate literature review (selected refs)
  - Outline/directory help; right‑click intents for editors
  - Persist results in `ai_artifacts`; stream events to Notifications

## Reference Intelligence

- Suggestion service (`backend/app/services/references/suggest.py`)
  - Candidate ranking by keywords/embeddings (implementation detail hidden behind interface)
  - Approve/reject transitions with confidence and audit

- Linking helpers (`backend/app/services/references/link.py`)
  - Attach approved references to papers

## Collaboration (Project & Paper)

- Membership & Invites
  - Projects and papers: list/add/remove/changerole; invite by email; accept/revoke.

- Comments & Activity
  - CRUD comments; resolve/unresolve; activity feed entries for key events.

- Presence & Realtime
  - WebSocket presence, typing, cursors; auth on join.

## Frontend Routing & Navbar

- Minimal navbar (icons only): Projects (`/projects`), Profile (`/profile`), Settings (modal or `/settings`).
- Landing `/projects` shows: Create Project CTA + All Projects (grid/table, search/sort).
- Project detail `/projects/:id` tabs: Overview | Discussion | Papers | References | Updates.
- Paper workspace `/projects/:id/papers/:paperId` tabs: Writing | Discussion.
- Editors on separate routes: `/editor/latex` and `/editor/rtf` under the paper workspace.
- Redirect legacy routes (`/dashboard`, `/papers/:id`) to new equivalents.

## Frontend Screens & Components

- Projects Home (`frontend/src/pages/projects/ProjectsHome.tsx`)
  - Create project; projects grid/table; filters/search; collaborators preview.

- Project tabs
  - Overview: edit idea/keywords; latest AI summaries; updates feed.
  - Discussion: project‑scoped chat, meeting upload/progress, MoM/action items; "Create paper from summary" shortcut.
  - Papers: list/create; choose LaTeX/RTF.
  - References: Suggested/Approved/Rejected; approve/reject; attach to papers.
  - Updates: notifications feed.

- Paper workspace
  - Writing: LaTeX or RTF editor page; AI tools; right‑click intents; fixed split view (resizing removed; already implemented for LaTeX).
  - Discussion: paper‑scoped chat; decisions log.

- Collaboration UI
  - Share dialogs, members lists, presence avatars, comments panel, activity feed.

- Settings
  - Theme toggle (light/dark/system) applied at app root.
  - AI model/provider/base URL/key; saved server‑side per user; updates AI features app‑wide.

## Feature Flags & Phasing

Flags (all default OFF; enable per environment):

- `PROJECTS_API_ENABLED`
- `PROJECT_FIRST_NAV_ENABLED`
- `PROJECT_REFERENCE_SUGGESTIONS_ENABLED`
- `PROJECT_AI_ORCHESTRATION_ENABLED`
- `PROJECT_COLLAB_REALTIME_ENABLED`
- `PROJECT_MEETINGS_ENABLED`
- `PROJECT_NOTIFICATIONS_ENABLED`

Phases:

1) Data + APIs (M1–M2): ship backend behind flags; keep legacy UI intact.
2) Routing + Projects Home (M3): enable `PROJECT_FIRST_NAV_ENABLED` for internal users; dual routes active.
3) References + AI scoping (M4): enable `PROJECT_REFERENCE_SUGGESTIONS_ENABLED`, `PROJECT_AI_ORCHESTRATION_ENABLED` per project.
4) Collaboration (M5): enable `PROJECT_COLLAB_REALTIME_ENABLED`; test invites, comments, presence.
5) Meetings + Notifications (M6): enable `PROJECT_MEETINGS_ENABLED`, `PROJECT_NOTIFICATIONS_ENABLED`.
6) Cutover (M7): redirect legacy routes; mark old endpoints deprecated.

## Deprecations & Redirects

- Keep `/dashboard` and `/papers/:id` available for two releases with 302 redirects + UI toast indicating new locations.
- OpenAPI marks legacy endpoints as `deprecated: true`.

## Validation & QA

Automated tests:

- Backend: projects, papers, membership, invites, comments, presence auth, references approve/reject, AI jobs, meetings, notifications.
- Frontend: routing, navbar icons, projects home, project tabs, editor intents, chat scoping, invites/comments/presence flows.

Manual tests (author under `tests/manual/...`; evidence in `tests/manual/_evidence/`):

- Landing shows Create Project CTA and complete list of projects; search/sort works.
- Project: idea/keywords → suggestions → approvals → attach to paper.
- Project chat vs paper chat isolation and context scoping.
- Create paper from discussion; summarize; generate literature review.
- Collaboration: invite users, role changes, inline comments, presence/cursors in LaTeX editor.
- Meetings: upload → transcribe → MoM/action items → seed paper creation.
- Notifications feed updates on AI jobs and comments.

## Rollback Plan

- DB: reversible migrations per revision; retain paper→project mapping artifacts from backfill.
- UI: disable feature flags to revert to legacy navigation and hide new features.
- API: keep legacy endpoints active during rollback window; OpenAPI indicates status.

## Ownership & Communication

- Backend: models/migrations (M1), services & APIs (M2), realtime & RBAC (M5), meetings (M6).
- Frontend: routing/layout (M3), projects UI (M3), references & AI scoping (M4), collaboration UI (M5), meetings & notifications (M6).
- QA: test plans, manual tests, E2E scripts per phase.
- Docs: this migration, plus runbooks in `docs/` (API usage, flags, and cutover checklist).

## Cutover Checklist (M7)

- [ ] All papers have non‑NULL `project_id`.
- [ ] Legacy routes redirect and are marked deprecated.
- [ ] Feature flags enabled as per rollout plan.
- [ ] Manual tests executed; critical paths pass.
- [ ] Stakeholder sign‑off for navigation change (landing → `/projects`).
