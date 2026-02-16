# Architecture Decision Records

This document captures the key architectural decisions made during the development of ScholarHub, a collaborative academic research platform. Each entry follows the Context-Decision-Alternatives-Consequences format.

---

## ADR-1: Y.js/Hocuspocus for Real-Time Collaboration

**Context.** ScholarHub requires real-time collaborative editing of LaTeX documents, including cursor presence, conflict-free merging, and resilience to intermittent connectivity.

**Decision.** We use Y.js as the CRDT library and Hocuspocus as the WebSocket server. The frontend integrates via `y-codemirror.next` for CodeMirror 6 binding (`frontend/src/components/editor/hooks/useRealtimeSync.ts`). The server (`collab-server/index.mjs`) runs Hocuspocus with Redis-based cross-instance synchronization and JWT authentication. Document state is bootstrapped from the backend database on first load (via the `onLoadDocument` hook fetching from `/api/v1/collab/bootstrap/`) and synchronized across connected clients through Y.js shared types (`Y.Text`), with atomic transactions for bootstrap operations to prevent duplication.

**Alternatives considered.**
- *Operational Transformation (OT):* Requires a central authority to serialize operations, adding complexity in the server-side transform layer and making offline editing more difficult.
- *Firebase/Firestore:* Proprietary lock-in with limited control over conflict resolution and data residency.
- *ShareDB:* OT-based, less mature ecosystem for editor integrations compared to Y.js.

**Consequences.** CRDTs merge edits without a central sequencer, enabling offline-first editing. The Y.js ecosystem provides production-ready bindings for CodeMirror (`y-codemirror.next`), awareness protocol for cursor presence, and Redis extension for multi-server scaling. Trade-off: CRDT metadata increases document size slightly compared to OT approaches.

---

## ADR-2: Policy-in-Code for AI Intent Routing

**Context.** The discussion AI must route user messages to appropriate tools (paper search, library lookup, project update) before invoking the LLM. This routing must be deterministic, testable, and free of LLM cost.

**Decision.** We implement a pure-Python `DiscussionPolicy` class (`backend/app/services/discussion_ai/policy.py`) that uses regex patterns and keyword matching to classify intent, extract search parameters (paper count, year bounds, open-access filters), and resolve search context through a priority chain. The policy produces a `PolicyDecision` dataclass with deterministic tool routing before any LLM call.

**Alternatives considered.**
- *Prompt-only routing:* Embeds routing instructions in the system prompt. Non-deterministic, untestable, and wastes tokens on routing logic every request.
- *Fine-tuned classifier:* Requires labeled training data, ongoing maintenance, and still introduces probabilistic behavior at the routing layer.

**Consequences.** Routing is fully deterministic and unit-testable with zero LLM cost. The policy extracts year bounds, paper counts, open-access preferences, and deictic references ("this topic") through regex, then resolves the effective search topic via a five-level priority chain (explicit user topic, memory hint, last search, project context, fallback). Trade-off: adding a new intent category requires code changes rather than prompt edits.

---

## ADR-3: pgvector Over Separate Vector Database

**Context.** ScholarHub needs vector similarity search for semantic paper matching and search reranking. Embeddings are generated via SentenceTransformers (384-dim, `all-MiniLM-L6-v2`) and stored alongside relational data.

**Decision.** We use the `pgvector` extension within PostgreSQL (`pgvector/pgvector:pg15` Docker image) rather than a dedicated vector database. Embeddings are stored as `VECTOR(384)` columns in the `paper_embeddings` table (`backend/app/models/paper_embedding.py`), with HNSW indexes for approximate nearest-neighbor search (`backend/alembic/versions/20260202_add_paper_embeddings.py`). The `EmbeddingService` (`backend/app/services/embedding_service.py`) provides a provider-abstracted interface with in-memory caching.

**Alternatives considered.**
- *Pinecone:* Managed service with excellent performance but adds external dependency, network latency for every query, and per-query cost.
- *Weaviate/Milvus:* Powerful but require deploying and operating a separate stateful service alongside PostgreSQL.

**Consequences.** All data lives in a single PostgreSQL instance: relational queries and vector similarity search use the same connection, simplifying joins (e.g., filtering embeddings by project ownership via foreign keys). Operational overhead is minimal since pgvector is a PostgreSQL extension, not a separate service. HNSW indexing provides low-latency approximate search at our current scale. Trade-off: at very large scale (millions of high-dimensional vectors), a purpose-built vector database may offer better throughput.

---

## ADR-4: OpenRouter for Multi-Model AI Access

**Context.** ScholarHub supports multiple AI models (GPT-4o, Claude, Gemini, DeepSeek, Llama, Qwen) for the discussion assistant, allowing users to choose their preferred model or bring their own API key.

**Decision.** We route all LLM requests through OpenRouter's unified API (`backend/app/services/discussion_ai/openrouter_orchestrator.py`). The `OpenRouterOrchestrator` extends the base `ToolOrchestrator`, using the OpenAI-compatible client pointed at `https://openrouter.ai/api/v1`. A three-tier model catalog fallback (remote API with 24-hour cache, local JSON fallback file, hardcoded defaults) ensures availability. Reasoning-tag filtering handles model-specific output formats.

**Alternatives considered.**
- *Direct API keys per provider:* Each provider (OpenAI, Anthropic, Google) requires a separate client, auth flow, and error-handling path. Model switching would require provider-specific code.
- *Custom proxy/gateway:* Building our own routing layer duplicates OpenRouter's functionality without the model catalog, rate-limit management, or fallback infrastructure.

**Consequences.** A single API integration supports 200+ models with unified tool-calling semantics. Users can switch models per-conversation without backend changes. The fallback chain (`openrouter_models_fallback.json`) ensures the model selector works even when the OpenRouter API is unreachable. Trade-off: dependency on OpenRouter as an intermediary adds a small latency overhead and requires handling provider-specific quirks (e.g., reasoning tags, XML tool calls) at the streaming layer.

---

## ADR-5: CodeMirror 6 for LaTeX Editor

**Context.** The LaTeX editor requires syntax highlighting, autocompletion, code folding, spell checking, real-time collaboration bindings, and track-changes decorations.

**Decision.** We use CodeMirror 6 with a custom extension stack (`frontend/src/components/editor/hooks/useCodeMirrorEditor.ts`). Extensions include LaTeX language support (`latexLanguageSetup.ts`), autocompletion (`latexAutocomplete.ts`), code folding (`latexFoldService.ts`), spell checking (`latexSpellcheck.ts`), error markers (`latexErrorMarkers.ts`), and track-changes decorations (`trackChangesDecoration.ts`). Real-time collaboration integrates via `y-codemirror.next` (`useRealtimeSync.ts`).

**Alternatives considered.**
- *Monaco (VS Code editor):* Heavier bundle, designed for IDE-like experiences. Y.js integration is less mature than `y-codemirror.next`.
- *Ace Editor:* Legacy architecture, limited extensibility for custom decorations like track changes.
- *ProseMirror:* Designed for rich-text, not source-code editing. Would require significant adaptation for LaTeX source mode.

**Consequences.** CodeMirror 6's modular architecture allows composing exactly the extensions needed. The `y-codemirror.next` binding provides first-class Y.js integration with cursor awareness and undo-manager support. Custom extensions for LaTeX folding (section/environment folding), autocomplete (commands, environments, citations), and track changes integrate cleanly through the facet/extension system. Trade-off: CodeMirror 6's API is lower-level than Monaco, requiring more custom code for IDE-like features.

---

## ADR-6: Tectonic for LaTeX Compilation

**Context.** ScholarHub compiles LaTeX documents server-side to produce PDF output. The compilation engine must be installable in a Docker container without a multi-gigabyte TeX Live distribution.

**Decision.** We use Tectonic (`v0.15.0`), installed as a single binary in the backend Docker image (`backend/Dockerfile`). The compilation endpoint (`backend/app/api/v1/latex.py`) invokes Tectonic via subprocess, with content-hash-based caching to avoid recompilation. A warmup pass on startup (`backend/app/services/latex_warmup.py`) primes Tectonic's package cache so first-user compilations are fast.

**Alternatives considered.**
- *TeX Live:* Full installation is 4-7 GB, dramatically increasing Docker image size and build time. Package management is manual.
- *LaTeX.js (client-side):* Limited subset of LaTeX supported; cannot handle real academic templates, BibTeX, or custom style files.

**Consequences.** Tectonic is a single ~15 MB binary that auto-downloads only the packages each document actually uses, keeping the Docker image small. It handles BibTeX processing internally. The warmup pass ensures common packages are pre-cached. Trade-off: Tectonic supports fewer niche LaTeX packages than a full TeX Live installation, though coverage is sufficient for standard academic templates.

---

## ADR-7: Docker Compose for Deployment

**Context.** ScholarHub runs on a single VPS (production at `scholarhub.space`) and consists of multiple services: FastAPI backend, React frontend, PostgreSQL, Redis, Hocuspocus collab server, OnlyOffice, and Jitsi.

**Decision.** We use Docker Compose for both local development (`docker-compose.yml`) and production (`docker-compose.prod.yml`). Services are connected via Docker networking with health checks. Production uses nginx as a reverse proxy with TLS termination. Local development mounts source directories for hot reload.

**Alternatives considered.**
- *Kubernetes:* Designed for multi-node orchestration with horizontal scaling. Significant operational overhead (control plane, ingress controllers, persistent volume claims) for a single-server deployment.
- *Dokku/Kamal:* Lighter alternatives that provide git-push deployment and container management. Dokku is single-server focused but opinionated about routing and add-ons. Kamal handles multi-service deployment well but adds its own abstraction over Docker. Neither provides the same transparent control over service composition as a plain Compose file.
- *Bare metal:* Direct process management via systemd. Loses container isolation, reproducible builds, and straightforward service dependency management.

**Consequences.** Docker Compose provides a single `docker-compose up` command to run the entire stack, with service dependencies expressed declaratively via `depends_on` with health checks. The same Compose file structure works identically in development and production with environment-variable overrides. Trade-off: scaling beyond a single server would require migrating to Kubernetes or a similar orchestrator.

---

## ADR-8: Cookie-Based JWT Authentication

**Context.** ScholarHub needs user authentication that works across the React SPA frontend and the FastAPI backend, supports OAuth (Google) alongside email/password registration, and remains secure against common web attacks (XSS, CSRF, token theft).

**Decision.** We use a dual-token cookie-based JWT strategy (`backend/app/core/security.py`, `backend/app/api/v1/auth.py`). Short-lived JWT access tokens (60-minute expiry) are issued with standard claims (`sub`, `exp`, `iat`, `iss`, `jti`) signed with HS256. Long-lived refresh tokens (7-day expiry) are opaque `secrets.token_urlsafe(32)` values stored as SHA-256 hashes in the database. Refresh tokens are delivered via `httpOnly`, `Secure`, `SameSite=Lax` cookies with a per-environment `COOKIE_DOMAIN` (e.g., `scholarhub.space` in production, `None` for localhost). Token rotation on every refresh stores the previous hash for single-use reuse detection: if a previously consumed refresh token is replayed, both tokens are revoked. Google OAuth follows the same token issuance flow, setting the refresh cookie on the `RedirectResponse` back to the frontend.

**Alternatives considered.**
- *Bearer-only tokens in localStorage:* Vulnerable to XSS exfiltration. No `httpOnly` protection for the refresh token.
- *Session-based auth (server-side sessions in Redis):* Adds stateful session storage, complicates horizontal scaling, and requires sticky sessions or a shared session store.
- *Third-party auth providers (Auth0, Clerk):* Adds external dependency, cost, and latency for every authentication check. Limits control over token claims and cookie configuration.

**Consequences.** Refresh tokens are invisible to JavaScript (`httpOnly`), limiting XSS impact to the access token's short lifetime. The `SameSite=Lax` policy mitigates CSRF for state-changing requests. Reuse detection provides automatic revocation on token compromise. Rate limiting on sensitive endpoints (`5/min` register, `10/min` login, `3/min` forgot-password) prevents brute force. Trade-off: per-environment `COOKIE_DOMAIN` configuration is required, and cookies must be set on `RedirectResponse` objects for OAuth flows to work correctly with browser redirect semantics.

---

## ADR-9: Multi-Source Paper Discovery Aggregation

**Context.** ScholarHub's paper discovery needs to search across academic databases comprehensively, since no single source provides complete coverage. Different sources have different strengths: arXiv for preprints, PubMed for biomedical literature, Semantic Scholar for citation data, OpenAlex for open metadata, and so on. The system must handle partial failures gracefully since any external API can be slow, rate-limited, or unavailable.

**Decision.** We implement a fan-out/fan-in aggregation architecture (`backend/app/services/paper_discovery/`) that queries up to 8 sources concurrently: arXiv, Semantic Scholar, Crossref, PubMed, OpenAlex, CORE, Europe PMC, and ScienceDirect. Each source is encapsulated in a `PaperSearcher` implementation (`backend/app/services/paper_discovery/searchers.py`) with source-specific query builders (`query_builder.py`) that translate the user query into each API's native syntax (e.g., arXiv field prefixes `ti:`/`abs:`, PubMed `[tiab]` tags, CORE Lucene syntax). A `SearchOrchestrator` (`backend/app/services/paper_discovery_service.py`) dispatches all searches concurrently behind a semaphore, collects results as they arrive, and supports early exit in fast mode once 3+ sources have returned sufficient results. Deduplication uses a two-pass strategy: first by normalized DOI, then by normalized title hash via MD5, always preferring the paper with the most complete metadata (scored by DOI presence, PDF URL, abstract length, author list). After deduplication, optional enrichers (Crossref metadata, Unpaywall open-access links) fill in missing fields. Ranking is pluggable via the `PaperRanker` interface, with four implementations: `LexicalRanker` (token overlap), `SimpleRanker` (weighted relevance + citations + recency with core-term boosts), `GptRanker` (LLM-scored relevance via OpenRouter), and `SemanticRanker` (combined lexical + bi-encoder + cross-encoder). A source-diversity cap (40% per source) prevents any single API from dominating results.

**Alternatives considered.**
- *Single-source search (Semantic Scholar or OpenAlex only):* Simpler integration but misses preprints (arXiv), biomedical coverage (PubMed/Europe PMC), and citation metadata (Crossref). No fallback if the chosen source is down.
- *Meta-search via a third-party aggregator (e.g., Dimensions, Lens.org):* Adds external dependency and API cost. Limited control over ranking, deduplication, and source-specific query optimization.
- *Sequential search with fallback:* Querying sources one at a time until enough results are found. Slower and biased toward whichever source is queried first.

**Consequences.** Fan-out search provides broad coverage and resilience: if any source times out or returns an error, the remaining sources still contribute results, tracked via per-source `SourceStats` (status, count, elapsed time). Source-specific query builders improve relevance by leveraging each API's native search capabilities rather than sending the same raw query everywhere. The two-pass deduplication prevents duplicate papers from appearing when the same work is indexed by multiple sources under different identifiers. Trade-off: querying 8 sources concurrently increases outbound API traffic and requires per-source rate limit handling; the system handles this via concurrency semaphores, per-source timeouts, and `RateLimitError` propagation.
