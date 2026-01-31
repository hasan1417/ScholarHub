# OpenRouter Orchestrator Action Plan

Date created: 2026-01-30
Owner: TBD
Status: Draft

## Context
This plan tracks follow-up work after review of:
- backend/app/services/discussion_ai/openrouter_orchestrator.py
- backend/app/services/discussion_ai/tool_orchestrator.py

Goal: keep a durable record of action items and progress to survive context loss.

## Verified Findings (from code review)
- Tool registry is modularized and _execute_tool_calls delegates to the registry.
- get_available_models supports require_tools filtering and uses cached model metadata.
- model_supports_reasoning uses cached flags first, then falls back to a hardcoded set.
- recent_search_id is passed through handle_message / handle_message_streaming.
- Fallback model catalog was hardcoded (now migrated to JSON file; see Progress Log).
- Streaming path uses _detect_paper_content (regex) to switch to "paper" mode.

## Non-Issues / Corrections
- No duplicate REASONING_SUPPORTED_MODELS list was found in smart_agent_service_v2_or.py.
- No large commented-out tool definition blocks found in tool_orchestrator.py.

## Action Items

### P0 - Decision: Model catalog strategy
Decision: JSON fallback file with env override.
Implementation:
- Default fallback file: backend/app/services/discussion_ai/openrouter_models_fallback.json
- Override path: OPENROUTER_FALLBACK_MODELS_PATH
Behavior: fetch from OpenRouter, fallback to JSON file, then to minimal builtin list if file missing.

Status: Completed

### P1 - Streaming "paper mode" safety
Problem: _detect_paper_content can misclassify and trigger "Creating paper" status early.
Goal: prevent false positives and avoid indefinite loading states.

Proposed changes:
- Gate paper-mode only after stronger signal (multiple LaTeX markers + min length).
- Resume streaming if no tool call arrives within N seconds.
- Only emit "Creating paper" status after tool call OR a verified threshold.

Status: Not started

### P1 - Tests for streaming state
Add tests that cover:
- False positive LaTeX markers without tool calls.
- True positive paper output with tool call.
- Timeout/resume streaming when tool call never arrives.

Status: Not started

### P2 - Documentation update
Record final decisions and any updated operational assumptions.

Status: Not started

## Progress Log
- 2026-01-30: Plan created from code verification. No changes made yet.
- 2026-01-30: P0 implemented. Hardcoded fallback list moved to JSON; optional env override added.
- 2026-01-30: Key resolution now prioritizes user BYOK, then server key for entitled users, then optional owner sharing.

## Next Steps
1) Implement streaming safety changes (P1).
2) Add tests for streaming logic (P1).
