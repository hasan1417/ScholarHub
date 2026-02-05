"""
Periodic cleanup service for the LaTeX compilation cache.

The LaTeX compiler (`api/v1/latex.py`) stores compilation artifacts under
`uploads/latex_cache/<hash>/`. Over time these accumulate and consume disk
space. This module provides:

- `cleanup_latex_cache()` -- synchronous function that deletes subdirectories
  older than a configurable threshold.
- `start_cache_cleanup_task()` -- async wrapper that runs the cleanup on a
  repeating interval as a background asyncio task.

Usage (from FastAPI startup):

    from app.services.latex_cache_cleanup import start_cache_cleanup_task

    @app.on_event("startup")
    async def startup():
        asyncio.create_task(start_cache_cleanup_task())
"""

import asyncio
import logging
import shutil
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def cleanup_latex_cache(
    cache_dir: str = "uploads/latex_cache",
    max_age_days: int = 7,
) -> int:
    """Delete subdirectories in *cache_dir* whose mtime exceeds *max_age_days*.

    Returns the number of directories that were successfully removed.
    """
    cache_path = Path(cache_dir).resolve()

    if not cache_path.is_dir():
        logger.info("LaTeX cache directory does not exist: %s -- nothing to clean", cache_path)
        return 0

    max_age_seconds = max_age_days * 86_400
    cutoff = time.time() - max_age_seconds
    cleaned = 0

    for entry in cache_path.iterdir():
        if not entry.is_dir():
            continue

        try:
            mtime = entry.stat().st_mtime
        except OSError as exc:
            logger.warning("Could not stat %s, skipping: %s", entry, exc)
            continue

        if mtime >= cutoff:
            continue

        try:
            shutil.rmtree(entry)
            cleaned += 1
            logger.warning(
                "Removed stale LaTeX cache directory: %s (age %.1f days)",
                entry.name,
                (time.time() - mtime) / 86_400,
            )
        except Exception as exc:
            logger.warning("Failed to remove %s: %s", entry, exc)

    return cleaned


async def start_cache_cleanup_task(interval_hours: int = 6) -> None:
    """Run :func:`cleanup_latex_cache` periodically in a background loop.

    The function uses ``asyncio.to_thread`` so file I/O does not block the
    event loop. It runs indefinitely until the task is cancelled (e.g. on
    application shutdown).
    """
    logger.info(
        "LaTeX cache cleanup task started (interval=%dh)",
        interval_hours,
    )

    interval_seconds = interval_hours * 3_600

    while True:
        try:
            cleaned = await asyncio.to_thread(cleanup_latex_cache)
            if cleaned:
                logger.info("LaTeX cache cleanup pass complete: removed %d entries", cleaned)
        except Exception as exc:
            logger.warning("LaTeX cache cleanup pass failed: %s", exc)

        await asyncio.sleep(interval_seconds)
