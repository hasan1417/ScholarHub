from fastapi import APIRouter, Request
from app.core.config import settings
import time
from app.services.discussion_ai.quality_metrics import get_discussion_ai_metrics_collector

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
        print(f"[metrics] {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {data}")
    except Exception:
        pass
    return {"ok": True}


@router.get("/metrics/discussion-ai")
async def get_discussion_ai_metrics():
    """Expose Discussion AI quality counters for observability dashboards."""
    if not settings.ENABLE_METRICS:
        return {"ok": True, "enabled": False, "data": {}}

    try:
        data = get_discussion_ai_metrics_collector().snapshot()
        return {"ok": True, "enabled": True, "data": data}
    except Exception as exc:
        return {"ok": False, "enabled": True, "error": str(exc)}


@router.post("/metrics/discussion-ai/reset")
async def reset_discussion_ai_metrics():
    """Reset Discussion AI counters (intended for QA/test environments)."""
    if not settings.ENABLE_METRICS:
        return {"ok": True, "enabled": False}

    try:
        get_discussion_ai_metrics_collector().reset()
        return {"ok": True, "enabled": True}
    except Exception as exc:
        return {"ok": False, "enabled": True, "error": str(exc)}


@router.get("/metrics/discussion-ai/history")
async def get_discussion_ai_metrics_history(
    hours: int = 24,
    limit: int = 120,
    aggregate_minutes: int = 1,
):
    """Expose time-bucketed Discussion AI quality metrics history."""
    if not settings.ENABLE_METRICS:
        return {"ok": True, "enabled": False, "data": []}

    hours = max(1, min(hours, 24 * 30))
    limit = max(1, min(limit, 2000))
    aggregate_minutes = max(1, min(aggregate_minutes, 24 * 60))
    try:
        data = get_discussion_ai_metrics_collector().history(
            hours=hours,
            limit=limit,
            aggregate_minutes=aggregate_minutes,
        )
        return {"ok": True, "enabled": True, "data": data}
    except Exception as exc:
        return {"ok": False, "enabled": True, "error": str(exc)}
