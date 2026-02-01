# OpenRouter Orchestrator Action Plan

Date created: 2026-01-30
Date completed: 2026-02-01
Owner: TBD
Status: Complete

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

Implemented changes:
- Increased early detection buffer threshold from 50 to 200 chars.
- Added min_length parameter (500 chars) for early detection calls.
- Strengthened LaTeX detection: require 1 primary + 1 secondary OR 3+ secondary indicators.
- Moved "Creating paper" status emission to auto-create phase (after full content received).
- Added resume mechanism: if early detection triggered but auto-create fails/doesn't match, content is streamed as fallback.

Status: Completed (2026-01-31)

### P1 - Tests for streaming state
Add tests that cover:
- False positive LaTeX markers without tool calls.
- True positive paper output with tool call.
- Timeout/resume streaming when tool call never arrives.

Implemented: backend/tests/test_paper_detection.py (19 tests)
- TestLaTeXDetection: 7 tests for LaTeX pattern matching
- TestMarkdownDetection: 4 tests for Markdown academic content
- TestStreamingScenarios: 4 tests for streaming edge cases
- TestEdgeCases: 4 tests for boundary conditions

Status: Completed (2026-01-31)

### P2 - Documentation update
Record final decisions and any updated operational assumptions.

Implemented:
- Added MODEL CATALOG FALLBACK STRATEGY comment block explaining the 3-tier fallback
- Added comprehensive docstring to _detect_paper_content explaining:
  - Why min_length is used (prevent false positives on short snippets)
  - Why LaTeX detection requires strong signals (1 primary + 1 secondary OR 3+ secondary)
  - Why Markdown detection needs title + academic sections
  - How the resume mechanism works (no silent failures)
- Added inline comment for latex_detected tracking

Status: Completed (2026-02-01)

## Progress Log
- 2026-01-30: Plan created from code verification. No changes made yet.
- 2026-01-30: P0 implemented. Hardcoded fallback list moved to JSON; optional env override added.
- 2026-01-30: Key resolution now prioritizes user BYOK, then server key for entitled users, then optional owner sharing.
- 2026-01-31: P1 streaming safety implemented. Strengthened detection thresholds, added resume mechanism.
- 2026-01-31: P1 tests added. 19 unit tests for paper detection in backend/tests/test_paper_detection.py.
- 2026-02-01: P2 documentation completed. Added inline docs for model fallback and paper detection.

## Next Steps
All planned items completed. Optional future work:
- Integration tests for full streaming flow
- Monitor false positive rates in production and adjust thresholds if needed
