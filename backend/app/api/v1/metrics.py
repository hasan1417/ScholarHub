from fastapi import APIRouter, Request
from app.core.config import settings
import time

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

