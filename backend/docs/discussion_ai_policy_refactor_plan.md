# Discussion AI Policy-First Refactor Plan

Date: 2026-02-07  
Status: Implemented (all phases completed)

## Implementation progress

Last updated: 2026-02-07

Current phase status:

- Phase A (Deterministic policy baseline): Completed.
- Phase B (Behavior-contract tests): Expanded and active.
- Phase C (Structured search contract + native filters): Core implementation completed.
- Phase D (Memory hardening + deterministic stage updates): Stage transition fix completed.
- Phase E (Prompt simplification): Initial simplification completed.
- Phase F (Replay regression harness): Completed with expanded deterministic coverage.
- Phase G (Decision logs + metrics): Completed with persistence, historical aggregation, and API export.

Completed in implementation so far:

- Added deterministic policy module:
  - `backend/app/services/discussion_ai/policy.py`
  - Introduced `SearchPolicy`, `PolicyDecision`, and `DiscussionPolicy`.
- Wired policy decision into non-streaming orchestrator:
  - `backend/app/services/discussion_ai/tool_orchestrator.py`
  - Added `_build_policy_decision(ctx)` and per-turn `ctx["policy_decision"]`.
  - Replaced duplicated direct-search detection/default logic with policy-backed methods.
  - Forced first-turn search fallback now uses policy defaults (`query`, `count`, `open_access_only`).
  - Direct-search guardrail in `_execute_tool_calls` now reads from `PolicyDecision`.
- Wired policy decision into streaming orchestrator:
  - `backend/app/services/discussion_ai/openrouter_orchestrator.py`
  - Streaming fallback candidate and forced `search_papers` execution now use `PolicyDecision`.
- Added behavior-contract tests:
  - `backend/tests/test_discussion_ai_contract.py`
  - Added tests for:
    - direct search decision defaults
    - non-search prompts not forced
    - text-only model response still forcing `search_papers` for direct-search intent
    - viewer read-only tool access still forcing deterministic `search_papers` on direct-search intent
- Extended policy with deterministic recency parsing:
  - `recent/latest` -> default last 5 years
  - `last N years`, `since YYYY`, and explicit `YYYY-YYYY` extraction
- Added structured search fields and propagation:
  - `backend/app/services/discussion_ai/tools/search_tools.py`
  - Added `limit`, `year_from`, `year_to` to `search_papers` schema.
  - `backend/app/services/discussion_ai/mixins/search_tools_mixin.py`
  - `_tool_search_papers` now accepts and emits structured filter fields in action payload.
- Wired native year/OA filters into discovery providers:
  - `backend/app/services/paper_discovery_service.py`
  - `backend/app/services/paper_discovery/interfaces.py`
  - `backend/app/services/paper_discovery/searchers.py`
  - Semantic Scholar receives native `year` (range) and `openAccessPdf=true`.
  - OpenAlex receives native `filter` (`from_publication_date`, `to_publication_date`, `is_oa:true`).
- Added deterministic stage transition on successful search tool execution:
  - `backend/app/services/discussion_ai/tool_orchestrator.py`
  - `backend/app/services/discussion_ai/openrouter_orchestrator.py`
  - Successful `search_papers`/`batch_search_papers` now enforces `research_state.stage = finding_papers` with history entry.
- Simplified prompt routing overlap (policy-first alignment):
  - `backend/app/services/discussion_ai/tool_orchestrator.py`
  - Removed duplicated direct-search default branching instructions from prompt.
  - Prompt now defers routing/default enforcement to policy code and keeps quality guidance.
- Added replay regression harness:
  - `backend/tests/fixtures/discussion_replays/policy_replays.json`
  - `backend/tests/test_discussion_ai_replays.py`
  - Fixture-driven replay checks now validate deterministic policy outputs across varied phrasings.
  - Coverage now enforces a minimum of 20 replay cases (currently 22).
- Added structured decision/action logging:
  - `backend/app/services/discussion_ai/tool_orchestrator.py`
  - Logs now include `PolicyDecision`, normalized search args, and deterministic stage transitions.
- Resolved role-policy drift for viewer routing:
  - `backend/app/services/discussion_ai/tool_orchestrator.py`
  - Viewer behavior now uses centralized permission filtering (read-only tools allowed).
  - Removed hardcoded "viewer has no tools" branch that prevented deterministic direct-search fallback.
  - Viewer system guidance now reflects read-only constraints (search/analyze allowed, write actions blocked).
- Added in-process quality counters for policy behavior:
  - `backend/app/services/discussion_ai/quality_metrics.py`
  - Tracks: direct-search tool-call rate, clarification-first rate, recency-filter compliance, and stage-transition success.
  - Uses Redis hash persistence sink with in-memory fallback.
- Added metrics export/reset API endpoints for dashboard integration:
  - `backend/app/api/v1/metrics.py`
  - `GET /api/v1/metrics/discussion-ai`
  - `POST /api/v1/metrics/discussion-ai/reset`
  - `GET /api/v1/metrics/discussion-ai/history` with `aggregate_minutes` for long-window rollups.
- Added metrics-focused regression tests:
  - `backend/tests/test_discussion_ai_metrics.py`
  - `backend/tests/test_discussion_ai_metrics_api.py`
  - `backend/tests/test_discussion_ai_metrics_persistence.py`
- Wired focused quality/replay suite into CI:
  - `.github/workflows/discussion-ai-quality.yml`

Verification evidence:

- `python -m pytest tests/test_discussion_ai_contract.py -v` -> 5 passed.
- `python -m pytest tests/test_ai_memory.py::TestDirectSearchRouting -v` -> 8 passed.
- `python -m py_compile ...` on changed files -> passed.
- Follow-up after structured filter + stage transition changes:
  - `python -m pytest tests/test_discussion_ai_contract.py -v` -> 8 passed.
  - `python -m pytest tests/test_ai_memory.py::TestDirectSearchRouting -v` -> 9 passed.
  - `python -m py_compile ...` on updated files -> passed.
- Replay and full focused regression suite:
  - `python -m pytest tests/test_discussion_ai_replays.py -v` -> 12 passed.
  - `python -m pytest tests/test_discussion_ai_replays.py tests/test_discussion_ai_contract.py tests/test_ai_memory.py::TestDirectSearchRouting tests/test_ai_memory.py::TestShouldUpdateFactsUrgency tests/test_ai_memory.py::TestUnansweredQuestionFixes -v` -> 44 passed.
- Metrics test suite:
  - `python -m pytest tests/test_discussion_ai_metrics.py -v` -> 2 passed.
  - `python -m pytest tests/test_discussion_ai_metrics_api.py tests/test_discussion_ai_metrics.py -v` -> 5 passed.
- Expanded focused regression suite:
  - `python -m pytest tests/test_discussion_ai_replays.py tests/test_discussion_ai_contract.py tests/test_ai_memory.py::TestDirectSearchRouting tests/test_ai_memory.py::TestShouldUpdateFactsUrgency tests/test_ai_memory.py::TestUnansweredQuestionFixes tests/test_discussion_ai_metrics.py tests/test_discussion_ai_metrics_api.py -v` -> 49 passed.
  - `python -m pytest tests/test_discussion_ai_replays.py tests/test_discussion_ai_contract.py tests/test_ai_memory.py::TestDirectSearchRouting tests/test_ai_memory.py::TestShouldUpdateFactsUrgency tests/test_ai_memory.py::TestUnansweredQuestionFixes tests/test_discussion_ai_metrics.py tests/test_discussion_ai_metrics_api.py tests/test_discussion_ai_metrics_persistence.py -v` -> 51 passed.
- Viewer-permission alignment regression checks:
  - `python -m pytest tests/test_discussion_ai_contract.py tests/test_ai_memory.py::TestDirectSearchRouting tests/test_discussion_ai_replays.py tests/test_discussion_ai_metrics.py tests/test_discussion_ai_metrics_api.py tests/test_discussion_ai_metrics_persistence.py -v` -> 39 passed.
  - `python -m pytest tests/test_tool_permissions.py tests/test_new_tool_registration.py -v` -> 40 passed.
- Final focused quality suite after replay expansion + metrics aggregation:
  - `python -m pytest tests/test_discussion_ai_replays.py tests/test_discussion_ai_contract.py tests/test_ai_memory.py::TestDirectSearchRouting tests/test_ai_memory.py::TestShouldUpdateFactsUrgency tests/test_ai_memory.py::TestUnansweredQuestionFixes tests/test_discussion_ai_metrics.py tests/test_discussion_ai_metrics_api.py tests/test_discussion_ai_metrics_persistence.py -v` -> 66 passed.

Known gaps after this slice:

- None for the scoped A-G refactor plan.

Next execution target:

- Optional: extend replay harness from policy-level to full conversation transcripts.

## Why this refactor exists

The current Discussion AI behavior has improved, but quality issues still appear as patch-to-patch regressions:

- Control flow can still drift because branching is split between prompt instructions and code paths.
- Scholar-quality constraints (for example `recent papers`) are not fully enforced as deterministic tool arguments.
- Stage transitions are not always persisted as deterministic state updates.
- Fixes can overfit one conversation pattern and regress another.

This plan moves the system to a policy-first architecture where deterministic code decides behavior, and the LLM focuses on language and synthesis.

## Scope

In scope:

- Deterministic intent routing for search-related turns.
- Structured search contract with native filters.
- Deterministic stage transitions for paper discovery workflow.
- Memory hardening for critical fields.
- Behavior-contract tests and replay regression harness.
- Decision logs and operational quality metrics.

Out of scope:

- Replacing the LLM provider.
- Redesigning library ingestion architecture.
- Broad schema expansion (`schema_memory_v2` style field explosion).

## Source of truth

Behavior correctness is defined by executable tests, not prose docs.

- Primary source of truth: `backend/tests/test_discussion_ai_contract.py` and `backend/tests/test_ai_memory.py`.
- This document is an implementation blueprint and rollout checklist.
- If this document conflicts with tests, tests win.

## Design principles

- Deterministic policy decides routing, defaults, and filters.
- LLM handles phrasing, summaries, and optional query enrichment.
- Critical memory/state fields have code fallbacks, not LLM-only extraction.
- Quality requirements map to explicit tool arguments.
- Every rule has a corresponding contract test.

## Dependency order

Execution order is fixed to reduce risk:

`2 -> 6 -> 3 -> 5 -> 4 -> 7 -> 8`

Mapped to phases below:

- Phase A: Policy layer baseline.
- Phase B: Behavior-contract tests alongside policy.
- Phase C: Structured search contract and native filters.
- Phase D: Memory and deterministic stage transitions.
- Phase E: Prompt simplification.
- Phase F: Replay regression harness.
- Phase G: Decision logs and metrics.

## Target architecture

### 1) Policy decision object

Introduce a single deterministic decision artifact produced before LLM generation:

```python
@dataclass
class PolicyDecision:
    intent: Literal["direct_search", "analysis", "clarify", "general"]
    force_tool: Optional[str]  # e.g., "search_papers"
    search: Optional[SearchPolicy]
    stage_transition: Optional[StageTransition]
    reasons: List[str]
```

```python
@dataclass
class SearchPolicy:
    topic: Optional[str]
    query_terms: List[str]
    year_from: Optional[int]
    year_to: Optional[int]
    open_access_only: Optional[bool]
    limit: int
```

### 2) Search execution contract

Search tool execution must be built from structured policy fields.

- `query` is still sent for provider compatibility.
- `year_from/year_to`, `open_access_only`, and `limit` are first-class fields.
- Freeform query text cannot remove deterministic constraints set by policy.

### 3) State transition contract

On successful `search_papers` execution:

- `ai_memory.research_state.stage` must become `finding_papers`.
- Transition is code-driven and not inferred from assistant prose.
- Transition reason should be logged.

## Phase plan

## Phase A: Deterministic policy baseline

Goal: deterministic routing for direct paper-search requests.

Deliverables:

- Add policy module: `backend/app/services/discussion_ai/policy.py`.
- Add pure functions for intent detection and search defaults.
- Integrate policy invocation in `tool_orchestrator.py` and `openrouter_orchestrator.py`.

Implementation notes:

- Keep classifier minimal and stable initially.
- Start with direct-search intent only.
- Avoid broad NLP heuristics in v1 policy.

Acceptance criteria:

- Direct request like `Can you find me recent papers on this topic?` always routes to search action.
- No clarification-only first response when policy marks `direct_search` and tool is available.

## Phase B: Behavior-contract tests (in parallel with Phase A)

Goal: lock expected behavior before wider refactor.

Deliverables:

- New test file: `backend/tests/test_discussion_ai_contract.py`.
- Contract tests for direct search routing and fallback behavior.

Required tests:

- `direct_search` request triggers `search_papers`.
- First response is not clarification-only for `direct_search`.
- Non-search conversational prompts do not force search.

Acceptance criteria:

- All contract tests pass locally and in CI.
- Failing tests clearly identify policy rule violated.

## Phase C: Structured search contract + native filters

Goal: enforce scholar-quality constraints via API params, not keyword stuffing.

Deliverables:

- Extend tool schema in `backend/app/services/discussion_ai/tools/search_tools.py`:
  - add `year_from`, `year_to`, `limit`.
- Update paper service adapters to pass native filters:
  - Semantic Scholar year filter handling.
  - OpenAlex publication date range filter handling.
- Keep backward-compatible fallback when providers reject unsupported filters.

Implementation notes:

- `recent` should resolve to deterministic window in policy (default: last 5 years unless user overrides).
- Do not append raw year lists to query text.
- `open_access_only` should be policy-derived and explicit.

Acceptance criteria:

- `recent papers` requests result in structured year filters.
- Search payload stores filter fields for auditability.
- Query quality no longer depends on year keywords.

## Phase D: Memory hardening + deterministic stage updates

Goal: critical memory fields are robust and reproducible.

Deliverables:

- Keep current direct RQ/topic extraction fallback paths.
- Add deterministic stage transition write after successful search execution.
- Ensure stage persistence happens in a single, testable path.

Acceptance criteria:

- After successful search in Test 2 pattern, stage is exactly `finding_papers` in `project_discussion_channels.ai_memory`.
- `research_question` and `research_topic` remain stable across short follow-up turns.

## Phase E: Prompt simplification

Goal: reduce prompt fragility once policy owns branching.

Deliverables:

- Reduce routing language in `BASE_SYSTEM_PROMPT`.
- Keep prompt focused on scholar tone, synthesis quality, and transparent reasoning.
- Remove competing instructions that imply optional clarifying detours when policy already forced action.

Acceptance criteria:

- Prompt no longer contains critical control-flow logic duplicated in code.
- Existing contract tests remain green without prompt-specific hacks.

## Phase F: Replay regression harness

Goal: prevent future regressions from silent behavior drift.

Deliverables:

- Add fixture replays in `backend/tests/fixtures/discussion_replays/`.
- Add replay runner asserting deterministic outputs:
  - intent
  - tool choice
  - filter fields
  - stage transitions

Acceptance criteria:

- Replay suite runs in CI.
- At least 20 representative transcripts covering search, memory, follow-up, and edge phrasing.

## Phase G: Decision logs + metrics

Goal: make debugging fast and objective.

Deliverables:

- Structured logs per turn:
  - policy intent
  - selected action
  - final tool args
  - stage transition result
  - reasons
- Add core metrics dashboard counters:
  - direct-search tool-call rate
  - clarification-first rate for direct-search intents
  - recency-filter compliance rate
  - stage transition success rate

Acceptance criteria:

- Logs enable root-cause analysis from one failing turn.
- Metrics detect regressions without manual SQL inspection.

## PR slicing strategy

PR 1:

- Phase A + minimal Phase B tests.
- No schema/tool API changes yet.

PR 2:

- Phase C + tests for recency and OA defaults.

PR 3:

- Phase D + memory/stage tests and SQL verification cases.

PR 4:

- Phase E prompt cleanup with no behavior regressions.

PR 5:

- Phase F replay harness.

PR 6:

- Phase G logging/metrics.

## Risk controls

- Feature-flag policy-first path for rapid rollback.
- Keep old query-only path as fallback during migration.
- Require contract test pass before each merge.
- Block release if recency compliance or stage transition rate drops.

## Definition of done

The refactor is complete when all are true:

- Direct search requests are deterministically routed to tool execution.
- `recent` is enforced via structured filters, not query text heuristics.
- Stage transitions are deterministic and persisted (`exploring` -> `finding_papers` on successful search).
- Contract tests and replay tests pass in CI.
- Decision logs and quality metrics are available in production.
- Prompt is no longer the primary source of control flow.

## Immediate implementation checklist

1. [x] Create `policy.py` with `PolicyDecision` and `SearchPolicy` dataclasses.
2. [x] Wire policy call in orchestrator before first LLM/tool decision.
3. [x] Add or update direct-search routing tests (contract file).
4. [x] Extend search tool schema with `year_from/year_to/limit`.
5. [x] Implement provider adapter support for native filters.
6. [x] Add deterministic stage update on successful search execution.
7. [x] Shrink prompt routing instructions after policy tests pass.
8. [x] Add replay harness fixtures and runner.
9. [x] Add structured logs and core quality counters.
