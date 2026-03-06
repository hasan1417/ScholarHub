# ScholarHub

Academic research platform — project management, paper discovery, collaborative LaTeX editing, AI discussion assistant.

## Stack
- **Frontend:** React + TypeScript + Vite, CodeMirror 6, Yjs realtime
- **Backend:** FastAPI + Python 3.11, SQLAlchemy + Alembic
- **Database:** PostgreSQL 15 + pgvector
- **Cache:** Redis 7
- **Infra:** Docker Compose, nginx reverse proxy

## Core Commands

- `cd frontend && npx tsc --noEmit` — TypeScript check (must pass before merge)
- `cd backend && python -m pytest tests/ -v` — Backend unit tests
- `cd backend && python -m pytest tests/test_policy_engine.py tests/test_discussion_ai_replays.py tests/test_discussion_ai_contract.py -v` — Core AI regression tests
- `docker compose up -d` — Start local dev (hot reload, no rebuild needed for code changes)
- `docker compose exec backend alembic upgrade head` — Run DB migrations

## Project Layout

```
backend/
  app/api/v1/          # FastAPI endpoints
  app/models/          # SQLAlchemy models
  app/schemas/         # Pydantic request/response schemas
  app/services/        # Business logic
    discussion_ai/     # AI assistant (tool orchestrator, OpenRouter, policy engine)
    paper_discovery/   # Multi-source paper search (Semantic Scholar, OpenAlex, CORE, etc.)
  alembic/             # DB migrations
  tests/               # pytest suite

frontend/
  src/components/      # React components
    editor/            # LaTeX editor (CodeMirror, Yjs, PDF preview)
    discussion/        # AI chat interface
  src/pages/           # Route pages
  src/services/api.ts  # Axios API client
  src/types/index.ts   # Shared TypeScript types
  src/hooks/           # Custom React hooks

collab-server/         # Hocuspocus Y.js collaboration server
```

## Conventions

- Python: type hints on all function signatures, Pydantic for validation, `logger` not `print`
- TypeScript: strict mode, no `any` without justification, React Query for server state
- Commits: `<Type>: <description>` (Add, Fix, Update, Refactor, Remove)
- Fix root causes, not symptoms. No over-engineering. Delete dead code immediately.
- Error handling at system boundaries only (API calls, DB queries, user input)

## Git Workflow

- `main` is the production branch
- PRs require: TypeScript check passes, backend tests pass
- No force-push to main

## Security Notes

- Auth via HTTP-only cookies (not localStorage)
- Production: `COOKIE_DOMAIN=scholarhub.space`, `DEBUG=false`
- Never commit `.env`, credentials, or API keys
- Validate all user input at API boundaries
