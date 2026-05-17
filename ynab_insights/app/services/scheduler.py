"""Background sync scheduling using APScheduler.

A single AsyncIOScheduler runs `run_sync` on a fixed interval. The job
itself short-circuits when YNAB credentials are not configured or when
another sync is already running.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.db import async_session_maker
from app.services.sync import SyncInProgressError, run_sync

logger = logging.getLogger(__name__)

JOB_ID = "ynab_sync"


async def scheduled_sync() -> None:
    """Single tick of the background sync. Safe to call concurrently with
    a manual `POST /sync`; in that case this tick is skipped."""
    settings = get_settings()
    if settings.ynab_token is None:
        logger.info("scheduled sync skipped: YNAB_TOKEN not configured")
        return
    try:
        async with async_session_maker() as session:
            result = await run_sync(session, settings.ynab_token)
        logger.info("scheduled sync complete: %s", result.model_dump())
    except SyncInProgressError:
        logger.info("scheduled sync skipped: another sync is in progress")
    except Exception:
        logger.exception("scheduled sync failed")


def build_scheduler() -> AsyncIOScheduler | None:
    """Return a configured scheduler, or None if scheduling is disabled."""
    settings = get_settings()
    if settings.sync_interval_minutes <= 0:
        logger.info("scheduler disabled (SYNC_INTERVAL_MINUTES <= 0)")
        return None

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        scheduled_sync,
        "interval",
        minutes=settings.sync_interval_minutes,
        id=JOB_ID,
        coalesce=True,
        max_instances=1,
    )
    return scheduler
