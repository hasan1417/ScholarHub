"""Background scheduler for project auto-discovery.

This module polls project discovery preferences on a fixed interval and
triggers auto-discovery runs for projects that have auto refresh enabled and
are overdue based on their configured refresh interval.

Usage (from FastAPI startup):

    from app.services.project_discovery_scheduler import start_auto_discovery_task

    @app.on_event("startup")
    async def startup():
        asyncio.create_task(start_auto_discovery_task())
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import inspect
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database import SessionLocal
from app.models import Project, ProjectDiscoveryRun, ProjectDiscoveryRunType, User
from app.services.project_discovery_service import ProjectDiscoveryManager

logger = logging.getLogger(__name__)

_DEFAULT_REFRESH_INTERVAL_HOURS = 24.0


def _discovery_storage_available(db: Session) -> bool:
    """Return whether the discovery run/result tables exist."""
    inspector = inspect(db.get_bind())
    required_tables = ("project_discovery_runs", "project_discovery_results")
    return all(inspector.has_table(table_name) for table_name in required_tables)


def _list_auto_refresh_project_ids(db: Session) -> list[UUID]:
    """Return project identifiers with auto discovery enabled."""
    rows = (
        db.query(Project.id)
        .filter(Project.discovery_preferences.contains({"auto_refresh_enabled": True}))
        .all()
    )
    return [row[0] for row in rows]


def _latest_auto_run_at(db: Session, project_id: UUID) -> Optional[datetime]:
    """Return the timestamp of the most recent auto discovery attempt."""
    latest_run = (
        db.query(ProjectDiscoveryRun.started_at, ProjectDiscoveryRun.completed_at)
        .filter(
            ProjectDiscoveryRun.project_id == project_id,
            ProjectDiscoveryRun.run_type == ProjectDiscoveryRunType.AUTO,
        )
        .order_by(ProjectDiscoveryRun.started_at.desc())
        .first()
    )
    if latest_run is None:
        return None
    return latest_run.completed_at or latest_run.started_at


def _normalize_timestamp(value: Optional[datetime]) -> Optional[datetime]:
    """Ensure timestamps are timezone-aware before interval comparisons."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _is_overdue(last_auto_run_at: Optional[datetime], refresh_interval_hours: float) -> bool:
    """Return whether a project's next auto discovery run is due."""
    normalized_last_run = _normalize_timestamp(last_auto_run_at)
    if normalized_last_run is None:
        return True

    due_at = normalized_last_run + timedelta(hours=refresh_interval_hours)
    return datetime.now(timezone.utc) >= due_at


async def _run_project_auto_discovery(project_id: UUID) -> None:
    """Execute one auto discovery run when the project is due."""
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        if project is None:
            logger.warning("Skipping auto discovery for missing project %s", project_id)
            return

        manager = ProjectDiscoveryManager(db)
        preferences = manager.as_preferences(project.discovery_preferences)
        if not preferences.auto_refresh_enabled:
            return

        refresh_interval_hours = (
            preferences.refresh_interval_hours or _DEFAULT_REFRESH_INTERVAL_HOURS
        )
        if preferences.refresh_interval_hours is None:
            preferences.refresh_interval_hours = refresh_interval_hours
        last_auto_run_at = _latest_auto_run_at(db, project.id)
        if not _is_overdue(last_auto_run_at, refresh_interval_hours):
            return

        owner = db.get(User, project.created_by)
        if owner is None:
            logger.warning(
                "Skipping auto discovery for project %s because owner %s was not found",
                project.id,
                project.created_by,
            )
            return

        logger.info(
            "Starting auto discovery for project %s (interval=%sh)",
            project.id,
            refresh_interval_hours,
        )
        await manager.discover_async(
            project,
            owner,
            preferences,
            max_results=preferences.max_results or 20,
            run_type=ProjectDiscoveryRunType.AUTO,
        )


async def start_auto_discovery_task() -> None:
    """Poll for overdue auto-discovery projects and run them in the background."""
    if not settings.AUTO_DISCOVERY_ENABLED:
        logger.info("Project auto discovery scheduler disabled")
        return

    logger.info(
        "Project auto discovery scheduler started (poll=%ss)",
        settings.AUTO_DISCOVERY_POLL_SECONDS,
    )

    while True:
        try:
            with SessionLocal() as db:
                if not _discovery_storage_available(db):
                    logger.warning(
                        "Project auto discovery skipped because discovery tables are unavailable"
                    )
                    project_ids: list[UUID] = []
                else:
                    project_ids = _list_auto_refresh_project_ids(db)

            for project_id in project_ids:
                try:
                    await _run_project_auto_discovery(project_id)
                except Exception:
                    logger.exception(
                        "Project auto discovery failed for project %s",
                        project_id,
                    )
        except Exception as exc:
            logger.warning("Project auto discovery scheduler pass failed: %s", exc)

        await asyncio.sleep(settings.AUTO_DISCOVERY_POLL_SECONDS)
