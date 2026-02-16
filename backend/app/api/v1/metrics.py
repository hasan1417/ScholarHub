import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user
from app.core.config import settings
from app.models.user import User
from app.services.discussion_ai.quality_metrics import get_discussion_ai_metrics_collector

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/metrics")
async def post_metrics(request: Request):
    if not settings.ENABLE_METRICS:
        return {"ok": True}
    try:
        data = await request.json()
    except Exception:
        data = {"raw": await request.body()}
    try:
        # Minimal console log; avoid PII, do not include headers
        logger.info("[metrics] %s %s", time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), data)
    except Exception:
        pass
    return {"ok": True}


@router.get("/metrics/discussion-ai")
async def get_discussion_ai_metrics(
    hours: int = 24,
    limit: int = 120,
    aggregate_minutes: int = 1,
    current_user: User = Depends(get_current_user),
):
    """Expose Discussion AI quality snapshot and history for observability dashboards."""
    if not settings.ENABLE_METRICS:
        return {"ok": True, "enabled": False, "snapshot": {}, "history": []}

    collector = get_discussion_ai_metrics_collector()
    try:
        snapshot = collector.snapshot()
    except Exception as exc:
        return {"ok": False, "enabled": True, "error": str(exc)}

    hours = max(1, min(hours, 24 * 30))
    limit = max(1, min(limit, 2000))
    aggregate_minutes = max(1, min(aggregate_minutes, 24 * 60))
    try:
        history = collector.history(
            hours=hours,
            limit=limit,
            aggregate_minutes=aggregate_minutes,
        )
    except Exception as exc:
        logger.warning("Failed to load metrics history: %s", exc)
        history = []

    return {"ok": True, "enabled": True, "snapshot": snapshot, "history": history}


@router.post("/metrics/discussion-ai/reset")
async def reset_discussion_ai_metrics(
    current_user: User = Depends(get_current_user),
):
    """Reset Discussion AI counters (intended for QA/test environments)."""
    if not settings.DEBUG:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Metrics reset is only available in debug mode",
        )
    if not settings.ENABLE_METRICS:
        return {"ok": True, "enabled": False}

    try:
        get_discussion_ai_metrics_collector().reset()
        return {"ok": True, "enabled": True}
    except Exception as exc:
        return {"ok": False, "enabled": True, "error": str(exc)}
