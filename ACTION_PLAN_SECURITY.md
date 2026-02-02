# Security & Architecture Action Plan

Date created: 2026-02-01
Owner: TBD
Status: Draft

## Context
This plan tracks security and architecture improvements identified from code review of:
- backend/app/services/discussion_ai/tool_orchestrator.py
- backend/app/services/discussion_ai/openrouter_orchestrator.py
- backend/app/services/reference_ingestion_service.py
- backend/app/services/smart_agent_service_v2.py
- backend/app/api/v1/project_discussion.py

Goal: Address security vulnerabilities and architectural concerns in priority order.

---

## High Severity

### H1 - SSRF + Resource Exhaustion via PDF Ingestion
**Finding:** `_fetch_pdf` in `reference_ingestion_service.py` fetches untrusted `pdf_url` server-side with:
- No host allowlist/blocklist (can hit internal services, cloud metadata endpoints)
- No content size limit (can exhaust memory/disk)
- Follows redirects blindly
- 30s timeout but no streaming size cap

**Risk:** Attacker could:
- Probe internal network (SSRF)
- Fetch cloud metadata (169.254.169.254)
- Cause OOM with large files
- Tie up worker threads with slow responses

**Implemented Fix:**
- `_fetch_pdf_secure()` with comprehensive SSRF protection
- `_make_ip_pinned_request()` - connects to resolved IP directly (closes DNS rebinding gap)
  - For HTTPS: uses urllib3 with `server_hostname` for proper SNI and cert validation
  - For HTTP: connects to IP with Host header
- Blocks private/internal IPs (IPv4 + IPv6): 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16, 127.0.0.0/8, 169.254.0.0/16, fc00::/7, fe80::/10, etc.
- Manual redirect following with validation at each hop (max 5 redirects)
- DNS resolution once per hop, connection pinned to that IP
- Streaming to BytesIO with 50MB size limit (avoids memory spike from list + join)
- URL scheme validation (http/https only)
- IPv4-mapped IPv6 addresses also checked against IPv4 blocklist

**Tests:** 33 unit tests in `backend/tests/test_ssrf_protection.py`
- IP blocking (localhost, private ranges, cloud metadata, IPv6)
- URL scheme validation (blocks file://, ftp://, gopher://)
- DNS resolution validation
- SSRF attack scenarios
- `_fetch_pdf_secure` behavior tests (redirect following, size limits, content-type validation)

**Status:** Completed (2026-02-01)

---

### H2 - No Role-Based Tool Permission Checks
**Finding:** Discussion AI endpoints check project membership but not role. Any member (including viewers) can trigger write operations via AI tools:
- `add_to_library` - adds references to project
- `create_paper` - creates new papers
- `update_paper` - modifies paper content
- `update_project_info` - modifies project metadata

**Risk:** Viewers (read-only members) can modify project state through AI.

**Implemented Fix:**
1. Created `tools/permissions.py` with:
   - `TOOL_MIN_ROLE` mapping (viewer/editor/admin for each tool)
   - `normalize_role()` - handles enums, strings, None (fail-closed to viewer)
   - `can_use_tool()` - checks if role has permission
   - `filter_tools_for_role()` - filters tool schemas before LLM sees them
   - `get_permission_error()` - user-friendly error messages

2. Updated `tools/registry.py`:
   - `get_schema_list_for_role()` - filters tools by role
   - `execute()` checks permissions before running (fail-closed backup)

3. Updated both orchestrators:
   - `_get_user_role_for_project()` - gets user's role from membership
   - `_build_request_context()` adds `user_role` and `is_owner` to ctx
   - `_get_tools_for_user()` - filters tools based on ctx
   - `_call_ai_with_tools()` and streaming version filter tools

**Tool Categories:**
- Read (all): get_recent_search_results, get_project_references, get_reference_details, search_papers, discover_topics, batch_search_papers, deep_search_papers, focus_on_papers, analyze_across_papers, get_project_papers, get_project_info, get_created_artifacts, get_channel_resources, get_channel_papers
- Write (editor+): add_to_library, create_paper, update_paper, generate_section_from_discussion, create_artifact, analyze_reference
- Admin: update_project_info

**Notes:**
- `is_owner` flag is available in ctx for future `OWNER_ONLY_TOOLS` if needed
- Completeness test ensures all registered tools have permission mappings

**Tests:** 33 unit tests in `backend/tests/test_tool_permissions.py`
- Role normalization (6 tests)
- Permission checking per role (12 tests)
- Tool filtering (4 tests)
- Error messages (2 tests)
- Integration workflows (3 tests)
- Registry-to-permissions completeness (1 test)

**Status:** Completed (2026-02-01)

---

### H3 - Owner-Scoped Writes by Non-Owners
**Finding:** Same root cause as H2. `add_to_library` and other write tools don't verify caller's role.

**Proposed Fix:** Covered by H2 implementation.

**Status:** Completed (covered by H2)

---

### H4 - API-Level Role Enforcement (Bypass Risk)
**Finding:** Even with tool-level permissions, API endpoints (e.g., `project_discussion.py` actions)
can be called directly by clients and currently only enforce membership, not role.

**Risk:** Viewers can bypass AI tool gating and mutate project state via direct API calls.

**Implemented Fix:**
Added `roles=[ProjectRole.ADMIN, ProjectRole.EDITOR]` checks to write endpoints (excluding chat):

1. **project_discussion.py:**
   - `POST /channels/{id}/tasks` (create task)
   - `PUT /tasks/{id}` (update task)
   - `DELETE /tasks/{id}` (delete task)
   - `POST /paper-action` (AI-suggested actions)
   - `DELETE /channels/{id}/artifacts/{id}` (delete artifact)

2. **research_papers.py:**
   - `POST /` (create paper) - role check added when `project_id` is provided

**Policy for Viewers:**
- ✅ Can send/edit/delete their own messages (chat with AI)
- ✅ AI responds but has NO tools available (enforced in H2)
- ❌ Cannot create/edit/delete tasks
- ❌ Cannot execute paper actions (create/edit/add-reference)
- ❌ Cannot delete artifacts
- ❌ Cannot create papers in the project

**Notes:**
- Channel management endpoints already had role checks
- Message endpoints allow viewers (chat access) - tool restriction is at AI layer
- Defense-in-depth alongside tool-level permissions from H2

**Status:** Completed (2026-02-01)

---

## Medium Severity

### M1 - Context Window Uses Message Count, Not Tokens
**Finding:** `SLIDING_WINDOW_SIZE = 20` uses message count. Problems:
- One message could be 10 tokens or 10,000 tokens
- Tool outputs (now with full abstracts) can be very large
- Different models have different context limits (8k to 128k)
- No overflow protection

**Risk:** Context overflow causing API errors or truncated responses.

**Implemented Fix:**

1. Created `token_utils.py` with:
   - `tiktoken` integration for accurate token counting
   - Model-aware context limits (OpenAI, Anthropic, Google, DeepSeek, Meta, Qwen)
   - `count_tokens()`, `count_message_tokens()`, `count_messages_tokens()`
   - `get_context_limit()` - returns limit for any model
   - `get_available_context()` - calculates available budget after reserves
   - `fit_messages_in_budget()` - fits newest messages within token budget
   - `should_summarize()` - triggers at 80% context usage
   - `truncate_content()` - safely truncates at sentence boundaries

2. Updated `_build_messages()` in `tool_orchestrator.py`:
   - Replaced message-count windowing with token-based windowing
   - Calculates system prompt tokens first
   - Reserves tokens for response (4000) and tool outputs (8000)
   - Fits conversation history within remaining budget (max 16000 tokens)
   - Logs token usage: `[TokenContext] History: X/Y messages, Z/W tokens`

3. Updated memory summarization trigger:
   - Uses `should_summarize()` instead of message count
   - Triggers at 80% of model's context limit
   - Summarizes older half of conversation when triggered

**Status:** Completed (2026-02-01)

---

### M2 - Client Can Influence Search Context
**Finding:** Client sends `recent_search_results` in payload. While `search_id` correlation prevents spoofing library adds, the search results are used in AI context.

**Risk:** Prompt injection via crafted paper titles/abstracts in client-supplied results.

**Implemented Fix (Option A - Server-side storage):**

1. Created `search_cache.py` with Redis-backed storage:
   - `store_search_results(search_id, papers)` - stores with 1-hour TTL
   - `get_search_results(search_id)` - retrieves by search_id
   - Key format: `search_results:{search_id}`

2. Updated `_tool_search_papers()` in `tool_orchestrator.py`:
   - Stores search results in Redis after each search

3. Updated both API endpoints to fetch from server:
   - `project_discussion.py` - ignores client `recent_search_results`
   - `project_discussion_openrouter.py` - ignores client `recent_search_results`
   - Both fetch from Redis using `recent_search_id`
   - Logs when client-provided data is ignored

**Security improvement:** Client cannot inject malicious paper titles/abstracts into AI context.

**Status:** Completed (2026-02-01)

---

### M3 - Editor Anchor Verification Not Enforced
**Finding:** `smart_agent_service_v2.py` includes `anchor` field in edit proposals for verification, but:
- Backend just yields it to output stream
- No actual verification against document content
- Edits apply regardless of anchor match

**Risk:** AI could propose edits for wrong line ranges, corrupting document.

**Implemented Fix:**
In `frontend/src/components/editor/DocumentShell.tsx`:

1. Changed anchor verification from "warn and proceed" to "reject and fail":
   - Compares normalized anchor (first 40 chars, lowercase) against actual line content
   - Uses fuzzy matching: substring containment OR first 3 words match
   - Rejects edit with `return false` if anchor doesn't match

2. Added user-facing error toast:
   - Shows "Edit rejected: document changed at line X. Please regenerate."
   - Red styling to indicate error (vs green for success)
   - Longer display duration (5s vs 3s) for error messages

3. Updated toast system to support error/success variants

**Behavior:**
- AI proposes edit with `anchor` = first 30-50 chars of target line
- User approves edit in UI
- Frontend verifies anchor matches current document state
- If mismatch (document changed since AI analyzed it): reject + show error
- If match: apply edit normally

**Status:** Completed (2026-02-01)

---

### M5 - Verbose Tool Outputs (Library Results)
**Finding:** `get_project_references` returns full abstracts and analysis for all references.

**Risk:** Large libraries can flood context, especially with smaller models, reducing reasoning quality.

**Mitigation:** Token-based context management (M1) now automatically handles this:
- Conversation history is fitted within a 16000 token budget
- Model-aware limits prevent overflow
- Older messages are summarized when approaching limits

**Status:** Mitigated by M1 (2026-02-01)

---

### M6 - Attribution for Owner-Scoped Adds
**Finding:** `add_to_library` creates references under the project owner without recording who initiated the add.

**Risk:** Loss of audit trail; difficult to trace responsibility or undo actions.

**Implemented Fix:**
1. Added `added_by_user_id` column to `ProjectReference` model
2. Created migration `c7e91ecb3a2c_add_added_by_user_id_to_project_references`
3. Added foreign key to `users` table with `ON DELETE SET NULL`
4. Added index `ix_project_references_added_by_user_id` for efficient lookups
5. Updated `_tool_add_to_library` to set `added_by_user_id` from `ctx.get("current_user")`
6. Added relationship `added_by` to model for easy access

**Schema:**
```sql
added_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL
```

**Status:** Completed (2026-02-01)

---

### M4 - Auto-Create Paper Heuristic
**Finding:** `_auto_create_paper_from_content` in OpenRouter orchestrator creates papers when model outputs paper-like content without calling `create_paper` tool.

**Risk:** Unintended paper creation cluttering user's project.

**Implemented Fix (Option B - Remove entirely):**
- Removed `_detect_paper_content()` method
- Removed `_auto_create_paper_from_content()` method
- Removed `_extract_and_create_latex_paper()` method
- Removed `_extract_and_create_markdown_paper()` method
- Removed `_markdown_to_latex()` method
- Removed early LaTeX detection during streaming
- Removed all `latex_detected` tracking logic
- Deleted `backend/tests/test_paper_detection.py`

**Rationale:** If the AI should create a paper, it should explicitly call the `create_paper` tool. Auto-detection was a workaround for models that didn't use tools correctly - this is better solved via prompt engineering, not heuristics. Simpler code, no false positives, no unintended paper creation.

**Status:** Completed (2026-02-01)

---

## Low Severity

### L1 - Model Inference Retry on Transient Errors
**Finding:** OpenRouter model list fetch has 3-tier fallback (API → JSON file → builtin). But inference calls return error on failure with no retry.

**Risk:** Transient API errors (429, 503, timeouts) cause user-visible failures.

**Implemented Fix:** Retry with exponential backoff on **same model only** (no silent fallback to different models).

1. Added to `openrouter_orchestrator.py`:
   - `RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}`
   - `MAX_RETRIES = 3`, `INITIAL_BACKOFF_SECONDS = 1.0`
   - `_is_retryable_error()` - classifies errors as retryable or not
   - Updated `_call_ai_with_tools()` with retry loop
   - Updated `_call_ai_with_tools_streaming()` with retry on stream init

2. Retryable errors:
   - `RateLimitError` (429)
   - `APIStatusError` with 500, 502, 503, 504
   - `APIConnectionError`, `APITimeoutError`

3. Non-retryable (fail immediately):
   - 400 Bad Request, 401 Unauthorized, 403 Forbidden, 404 Not Found
   - Any other client errors

**Why NOT silent model fallback:**
- User chose the model intentionally (quality, cost, capabilities)
- Different models have different tool support and context limits
- Silent fallback masks real issues and confuses users
- Better to fail clearly and let user decide

**Tests:** 26 unit tests in `backend/tests/test_openrouter_retry.py`
- Error classification (12 tests)
- Non-streaming retry behavior (10 tests)
- Streaming retry behavior (3 tests)
- No client configured (2 tests)

**Status:** Completed (2026-02-02)

---

### L2 - Debug Logs May Leak Content
**Finding:** Discussion AI uses `print()` statements with content previews (OpenRouter + tool orchestrators).

**Risk:** Sensitive content in logs (PII, research data).

**Implemented Fix:**
Replaced all 17 `print()` statements with `logger.debug()` and sanitized sensitive content:

1. **openrouter_orchestrator.py** (6 → 4 statements):
   - Iteration/tool call info → `logger.debug()`
   - Content preview → removed (now logs length only)
   - Tool results dump → removed entirely
   - Actions → logs count and types only

2. **tool_orchestrator.py** (11 → 8 statements):
   - User role debug → removed email, uses `logger.debug()`
   - Token context → `logger.debug()`
   - Streaming status → `logger.debug()`
   - Tool results dump → removed (now logs tool names only)
   - Actions → logs count and types only

**Sanitization applied:**
- No content previews (could contain user research)
- No email addresses in logs
- No full tool results (could contain paper abstracts)
- Only metadata logged (counts, types, tool names)

**Note:** `logger.debug()` is not shown in production by default (requires DEBUG log level).

**Status:** Completed (2026-02-02)

---

### L3 - Integration Tests Missing
**Finding:** Tool orchestrator tests are mocked. No VCR-style integration tests that validate real API behavior.

**Risk:** Mocked tests may not catch real-world edge cases.

**Decision:** Skipped - not worth the complexity.

**Reasoning:**
- VCR-style tests don't work well with AI (non-deterministic responses, streaming)
- Current unit test coverage is strong (92+ tests for SSRF, permissions, retry, registry)
- API connectivity issues surface immediately in manual testing
- Maintenance burden of cassettes outweighs benefit

**Status:** Skipped (2026-02-02)

---

## Priority Order

1. **H1** - SSRF protection (security critical)
2. **H2** - Role-based permissions (security critical)
3. **H4** - API-level role enforcement (security critical)
4. **M1** - Token-based context management (reliability)
5. **M5** - Verbose tool outputs (context management)
6. **M3** - Anchor verification (data integrity)
7. **M4** - Auto-create confirmation (UX)
8. **M2** - Server-side search results (architecture)
9. **M6** - Attribution for owner-scoped adds (auditability)
10. **L1** - Inference fallback (reliability)
11. **L2** - Log sanitization (security hygiene)
12. **L3** - Integration tests (quality)

---

## Progress Log
- 2026-02-01: Plan created from security review findings.
- 2026-02-01: H1 v1. Initial SSRF protection (IP blocking, redirect validation, size limits).
- 2026-02-01: H1 v2. Fixed DNS rebinding gap with IP-pinned connections, added BytesIO streaming, expanded tests to 33.
- 2026-02-01: H2 completed. Tool-level permissions with filtering + execution checks. 32 tests.
- 2026-02-01: H2 v2. Added get_project_info to permissions, added registry completeness test. 33 tests.
- 2026-02-01: H3 completed (covered by H2).
- 2026-02-01: H4 completed. API-level role enforcement for write endpoints (excluding chat).
- 2026-02-01: H4 v2. Reverted message endpoints - viewers can chat but AI has no tools.
- 2026-02-01: M1 completed. Token-based context management with tiktoken, model-aware limits, automatic summarization.
- 2026-02-01: M5 mitigated by M1 token-based context management.
- 2026-02-01: M2 completed. Server-side search cache in Redis, client-provided results ignored.
- 2026-02-01: M3 completed. Editor anchor verification enforced - edits rejected if document changed since AI analysis.
- 2026-02-01: M4 completed (Option B). Removed auto-create paper feature entirely - AI must use create_paper tool explicitly.
- 2026-02-01: M6 completed. Added `added_by_user_id` column to track who added each reference.
- 2026-02-01: Frontend fix - Clear ingestion states on new search so "Found X papers" notification shows instead of stale "X papers added" bar.
- 2026-02-01: Investigated search quality issue - identified root cause (query over-expansion + Semantic Scholar rate limiting + arXiv relevance ranking). Fix deferred.
- 2026-02-02: L1 completed. Added retry with exponential backoff for transient API errors (429, 5xx, timeouts). No silent model fallback - user chose their model intentionally.
- 2026-02-02: L2 completed. Replaced 17 print() statements with logger.debug(), sanitized sensitive content (no content previews, no emails, no full tool results).
- 2026-02-02: L3 skipped. VCR-style tests not suitable for AI (non-deterministic, streaming). Current 92+ unit tests provide sufficient coverage.
- 2026-02-02: Backlog - Spinner fix completed. Update displayMessage immediately on first token to hide spinner during tool calling.
- 2026-02-02: Phase 4.1 completed. Added `get_related_papers` tool with Semantic Scholar priority and OpenAlex fallback. Supports similar/citing/references relations.

## Next Steps
All planned items complete. Only Phase 4.2 (Semantic Search with embeddings) remains as future work.

## Backlog (Deferred)

### Search Quality Enhancement

**Goal:** Improve search results to match Google Scholar quality.

**Current State:**
- 4 sources active: arXiv, Semantic Scholar, OpenAlex, Crossref
- Simple ranking: title/abstract token overlap (`title_overlap * 3 + abstract_overlap`)
- No retry on rate limits
- No query understanding (synonyms, related terms)

**Implementation Order:**
1. 1.1 Telemetry (measure first)
2. 1.3 Core Terms Boost (direct quality win)
3. 1.2 Retry (reliability polish)
4. 2.3 Verify Deduplication
5. 2.1 Citation-Weighted Ranking
6. 2.2 Enable More Sources (one at a time)
7. Phase 3-4 as needed

---

#### Phase 1: Core Quality Fixes (High Priority)

**Recommended order:** 1.1 → 1.3 → 1.2 (telemetry first to measure, then direct quality fix, then reliability)

**1.1 Search Telemetry Logging** ✅ COMPLETED
```python
# SearchOrchestrator logs:
logger.info(f"[Search] START query='{query}' | max_results={max_results} | sources={sources} | fast_mode={fast_mode}")
logger.info(f"[Search] COMPLETE query='{query}' | results={N}/{M} (returned/deduped) | counts={...} | times_ms={...} | rate_limited={...} | degraded={...} | total_elapsed={X}s")

# PaperDiscoveryService logs:
logger.info(f"[Discovery] query='{query}' → enhanced='{best_query}' | papers={N} | sources={...} | rate_limit_pct={X}% | timings={{enhance=Xs, search=Xs, total=Xs}}")
```
- Log query, enhanced query, sources used, per-source counts
- Log per-source elapsed times (ms) and statuses
- Log rate-limit hits (count + percentage)
- Log degraded sources (timeout, rate_limited, error)
- Added `elapsed_ms` field to `SourceStats` dataclass
- **Why first:** Required to measure impact of all subsequent changes
- **Status:** Completed (2026-02-02)

**1.2 Semantic Scholar Retry with Timeout** ⏭️ SKIPPED
- Per-source time budget: 1.5-2s max
- Retry 2x with short backoff (200ms, 400ms)
- **Decision:** Skipped - rate limits are not transient (100 req/5min without API key). Retrying 600ms later will still fail. Better solution: use API key (pending approval from Semantic Scholar).
- **Note:** Sources already run in parallel, so one failure isn't catastrophic. Other sources provide results.
- **Status:** Skipped (2026-02-02) - waiting for API key

**1.3 Core Terms Extraction + Scoring Boost** ✅ COMPLETED
- Define core terms: original query tokens + quoted phrases (stopwords filtered)
- Log core terms for debugging: `[CoreTerms] Extracted from '{query}': {terms}`
- Soft filter as scoring boost (not hard drop):
  - Core term in title: +20% boost (`core_term_title_boost`)
  - Core term in abstract: +10% boost (`core_term_abstract_boost`)
- Avoids dropping papers with valid synonyms
- Telemetry: `core_term_presence={pct}% ({hits}/{total})` in discovery summary
- **Implementation:**
  - `extract_core_terms()` in `query.py` - extracts words + quoted phrases
  - `SimpleRanker` applies boosts during scoring
  - Core terms passed from service → orchestrator → ranker
- **Note:** Boost values are initial estimates - measure with telemetry and adjust
- **Status:** Completed (2026-02-02)

---

#### Phase 2: Better Ranking (Medium Priority)

**2.1 Citation-Weighted Ranking** ✅ COMPLETED
- Ranking formula: **50% relevance + 30% citations + 20% recency**
- Citation scores use recency-adjusted formula to prevent old papers from dominating:
  ```
  adjusted_citations = citations / log(years_since_publish + 1)
  ```
- Log-scaled citations to prevent mega-papers from dominating (~10,000 adjusted = max score)
- Recency bonus: Current year = 1.0, 50% decay over 5 years, slower decay after
- Each component normalized within result set before combining
- **Test result:** Balances recent relevant work (2023, 0 cites, score 0.82) with classics (2014, 17k cites, score 0.67)
- **Status:** Completed (2026-02-02)

**2.2 Enable Additional Sources** ✅ COMPLETED
- Previously using 4: arXiv, Semantic Scholar, OpenAlex, Crossref
- **Enabled:** PubMed, Europe PMC (6 sources total)
- **Skipped:** CORE (unreliable, 500 errors), ScienceDirect (mostly paywalled)
- Updated in: `tool_orchestrator.py`, `project_discussion.py`
- **Test result:** 15 papers from pubmed (4) + europe_pmc (11) for "cancer immunotherapy"
- **Status:** Completed (2026-02-02)

**2.3 Verify Deduplication Quality** ✅ COMPLETED
- Cross-source deduplication verified working correctly
- **Implementation:**
  - Primary key: Normalized DOI (removes URL prefixes, lowercases)
  - Fallback: Normalized title hash (unicode normalization, punctuation removal)
  - When duplicates found, keeps paper with better metadata (DOI, PDF, abstract, etc.)
- **Test result:** 15 papers from 3 sources (crossref, semantic_scholar, arxiv) - no duplicates
- **Bugfix:** Added missing `xml.etree.ElementTree` import to `searchers.py` (was breaking PubMed)
- **Status:** Completed (2026-02-02)

---

#### Phase 3: Smarter Queries (Lower Priority)

**3.1 Source-Specific Query Builders** ✅ COMPLETED
- Created `query_builder.py` with optimized formatters for each source
- **arXiv:** Field prefixes `ti:` (title), `abs:` (abstract) for short queries
- **PubMed:** Field tag `[tiab]` for title/abstract matching
- **Europe PMC:** Field prefixes `TITLE:`, `ABSTRACT:`
- **Semantic Scholar, OpenAlex, Crossref:** Plain text (their NLP handles it well)
- **Status:** Completed (2026-02-02)

**3.2 Phrase Quoting for Short Queries** ✅ COMPLETED (included in 3.1)
- Short queries (2-3 words): Auto-quoted as phrases in field-specific search
- Quoted phrases in input: Preserved and searched in title/abstract
- Long queries: Pass through unchanged (default behavior)
- **Status:** Completed (2026-02-02)

---

#### Phase 4: Advanced Features (Future)

**4.1 Related Papers** ✅ COMPLETED
- Added `get_related_papers` tool to AI assistant
- Supports three relation types: `similar`, `citing`, `references`
- **Priority:** Semantic Scholar API (better recommendations) → OpenAlex fallback
- **Paper identifiers:** DOI, Semantic Scholar ID, OpenAlex ID, or title search
- Results cached for `add_to_library` integration
- **Implementation:**
  - Tool schema in `tools/search_tools.py`
  - Handler in `tool_orchestrator.py` with SS/OpenAlex dual-source logic
  - Permission: viewer level (read-only)
- **Status:** Completed (2026-02-02)

**4.2 Semantic Search (Embeddings)**
- Generate query embeddings
- Compare against paper embeddings
- Requires embedding storage/indexing
- **Status:** Not started

---

#### Metrics to Track

| Metric | Description | Target |
|--------|-------------|--------|
| Results per source | Count from each source | Balanced distribution |
| Rate limit hits | % of searches hitting 429 | < 5% |
| Core term presence | % results with core term in title/abstract | > 80% |
| Search latency | P50/P95 response time | < 2s / < 4s |

---

### Spinner Persists While Generating
**Finding:** Loading spinner continues to show during AI response generation, especially during tool calling scenarios.

**Impact:** UX - user sees spinner instead of streaming response.

**Implemented Fix:** In `ProjectDiscussionOR.tsx`, update `displayMessage` immediately on first token (no debounce) and clear `isWaitingForTools` flag. Subsequent tokens are still throttled (30ms).

**Status:** Completed (2026-02-02)

---

### LaTeX Editor - Ask Follow-up on Vague Requests
**Finding:** The LaTeX editor AI should ask clarifying questions when user requests are vague or ambiguous.

**Impact:** UX - AI may generate content that doesn't match user intent.

**Proposed Fix:** Add logic to detect vague prompts and use AskUserQuestion-style flow before generating.
