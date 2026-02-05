import asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from app.api.v1 import auth, users, research_papers, documents, ai, team, branches, discovery, references, latex, onlyoffice, metrics, comments, section_locks, collab, collab_bootstrap, snapshots, subscription
from app.core.config import settings
from app.core.rate_limiter import init_rate_limiter
from app.database import engine
import time
from sqlalchemy import text
from typing import Dict
from app.services.latex_warmup import warmup_latex_cache
from app.services.latex_cache_cleanup import start_cache_cleanup_task
from app.services.document_processing_service import warmup_marker_background
try:
    import redis as redis_lib
except Exception:  # pragma: no cover
    redis_lib = None

app = FastAPI(
    title="ScholarHub API",
    description="AI-Powered Research Paper Management Platform",
    version="1.0.0"
)

# Session middleware for OAuth state management
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# CORS middleware (configured via settings for production safety)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Exchange-Id"],
)

# Initialize rate limiter
init_rate_limiter(app)

# Serve static files (assets)
try:
    static_dir = (Path(__file__).resolve().parent.parent / "static").resolve()
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
except Exception:
    pass

try:
    uploads_dir = (Path(__file__).resolve().parent.parent / settings.UPLOADS_DIR).resolve()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/uploads", StaticFiles(directory=str(uploads_dir)), name="uploads")
except Exception:
    pass

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "ScholarHub Backend"}

# Detailed health including DB and Redis
@app.get("/healthz")
async def health_detailed() -> Dict[str, object]:
    resp: Dict[str, object] = {"service": "ScholarHub Backend", "status": "healthy"}

    # DB check
    t0 = time.time()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        resp["db"] = {"status": "ok", "elapsed_ms": round((time.time() - t0)*1000.0, 2)}
    except Exception as e:
        resp["db"] = {"status": "error", "error": str(e), "elapsed_ms": round((time.time() - t0)*1000.0, 2)}
        resp["status"] = "degraded"

    # Redis check (if available)
    if redis_lib:
        t1 = time.time()
        try:
            client = redis_lib.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=1, socket_timeout=1)
            pong = client.ping()
            resp["redis"] = {"status": "ok" if pong else "error", "elapsed_ms": round((time.time() - t1)*1000.0, 2)}
        except Exception as e:
            resp["redis"] = {"status": "error", "error": str(e), "elapsed_ms": round((time.time() - t1)*1000.0, 2)}
            resp["status"] = "degraded"
    else:
        resp["redis"] = {"status": "skipped"}

    return resp

# Include API routers
app.include_router(auth.router, prefix="/api/v1", tags=["authentication"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
if settings.PROJECTS_API_ENABLED:
    from app.api.v1 import projects  # local import so flag can disable route

    app.include_router(projects.router, prefix="/api/v1/projects", tags=["projects"])
if settings.PROJECT_REFERENCE_SUGGESTIONS_ENABLED:
    from app.api.v1 import project_references, project_discovery  # noqa: F401

    app.include_router(project_references.router, prefix="/api/v1", tags=["project references"])
    app.include_router(project_discovery.router, prefix="/api/v1", tags=["project discovery"])
if settings.PROJECT_AI_ORCHESTRATION_ENABLED:
    from app.api.v1 import project_ai  # noqa: F401

    app.include_router(project_ai.router, prefix="/api/v1", tags=["project ai"])
if settings.PROJECT_MEETINGS_ENABLED:
    from app.api.v1 import project_meetings  # noqa: F401

    app.include_router(project_meetings.router, prefix="/api/v1", tags=["project meetings"])
if settings.PROJECT_NOTIFICATIONS_ENABLED:
    from app.api.v1 import project_notifications  # noqa: F401

    app.include_router(project_notifications.router, prefix="/api/v1", tags=["project notifications"])
if settings.PROJECTS_API_ENABLED:
    from app.api.v1 import project_discussion, project_discussion_openrouter  # noqa: F401

    app.include_router(project_discussion.router, prefix="/api/v1", tags=["project discussion"])
    app.include_router(project_discussion_openrouter.router, prefix="/api/v1", tags=["project discussion openrouter"])
if settings.TRANSCRIBER_ENABLED:
    from app.api.v1 import transcription  # noqa: F401

    app.include_router(transcription.router, prefix="/api/v1", tags=["transcription"])
app.include_router(research_papers.router, prefix="/api/v1/research-papers", tags=["research papers"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["documents"])
app.include_router(ai.router, prefix="/api/v1/ai", tags=["ai features"])

# Smart Agent (experimental)
from app.api.v1 import agent  # noqa: F401
app.include_router(agent.router, prefix="/api/v1/agent", tags=["smart agent"])

# Smart Agent OpenRouter (Beta - multi-model support)
from app.api.v1 import agent_openrouter  # noqa: F401
app.include_router(agent_openrouter.router, prefix="/api/v1/agent-or", tags=["smart agent openrouter"])

app.include_router(team.router, prefix="/api/v1/team", tags=["team management"])
app.include_router(branches.router, prefix="/api/v1/branches", tags=["branch management"])
app.include_router(discovery.router, prefix="/api/v1/discovery", tags=["paper discovery & literature review"])
app.include_router(references.router, prefix="/api/v1/references", tags=["references"])
app.include_router(latex.router, prefix="/api/v1", tags=["latex"])
app.include_router(onlyoffice.router, prefix="/onlyoffice", tags=["onlyoffice"])
app.include_router(metrics.router, prefix="/api/v1", tags=["metrics"])
app.include_router(comments.router, prefix="/api/v1", tags=["comments"])
app.include_router(section_locks.router, prefix="/api/v1", tags=["section-locks"])
if settings.PROJECT_COLLAB_REALTIME_ENABLED:
    app.include_router(collab.router, prefix="/api/v1/collab", tags=["collaboration"])
    app.include_router(collab_bootstrap.router, prefix="/api/v1", tags=["collaboration"])

# Document history/snapshots
app.include_router(snapshots.router, prefix="/api/v1", tags=["document history"])

# Subscription management
app.include_router(subscription.router, prefix="/api/v1/subscription", tags=["subscription"])


@app.on_event("startup")
async def startup_warmup_event() -> None:
    """Warm up services on startup (non-blocking)."""
    # LaTeX cache warmup (async task)
    if settings.LATEX_WARMUP_ON_STARTUP:
        asyncio.create_task(warmup_latex_cache())

    # LaTeX cache cleanup (periodic background task)
    asyncio.create_task(start_cache_cleanup_task())

    # Marker PDF converter warmup (background thread - doesn't block event loop)
    # This loads the ML models so first PDF request doesn't timeout
    warmup_marker_background()

    # Start embedding worker for semantic search (background thread)
    try:
        from app.services.embedding_worker import start_embedding_worker
        start_embedding_worker()
    except Exception as e:
        # Don't fail startup if embedding worker fails
        import logging
        logging.getLogger(__name__).warning(f"Failed to start embedding worker: {e}")


@app.on_event("shutdown")
async def shutdown_event() -> None:
    """Cleanup on shutdown."""
    try:
        from app.services.embedding_worker import stop_embedding_worker
        stop_embedding_worker()
    except Exception:
        pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
