"""Background scheduling using APScheduler.

A single AsyncIOScheduler runs the YNAB sync on a fixed interval and the four
v2.4 Insight generators on cron schedules. Each job short-circuits when its
prerequisites aren't met (missing credentials, no budgets, feature flag off).
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.db import async_session_maker
from app.insights import InsightGenerator, execute_generator
from app.insights.cashflow_forecast import CashflowForecastGenerator
from app.insights.category_drift import CategoryDriftGenerator
from app.insights.goal_trajectory import GoalTrajectoryGenerator
from app.insights.spending_anomaly import SpendingAnomalyGenerator
from app.insights.subscription_audit import SubscriptionAuditGenerator
from app.insights.year_in_money import YearInMoneyGenerator
from app.services.queries import list_budgets_ordered
from app.services.sync import SyncInProgressError, run_sync

logger = logging.getLogger(__name__)

JOB_ID = "ynab_sync"

# Insight generator schedule. Times are UTC and chosen to fall after the most
# common sync cadences so generators see fresh YNAB data.
_INSIGHT_JOBS: tuple[tuple[str, type[InsightGenerator], dict[str, object]], ...] = (
    (
        "insights_subscription_audit",
        SubscriptionAuditGenerator,
        {"day_of_week": "mon", "hour": 3, "minute": 10},
    ),
    (
        "insights_spending_anomaly",
        SpendingAnomalyGenerator,
        {"day_of_week": "mon", "hour": 3, "minute": 20},
    ),
    (
        "insights_cashflow_forecast",
        CashflowForecastGenerator,
        {"hour": 3, "minute": 30},
    ),
    (
        "insights_goal_trajectory",
        GoalTrajectoryGenerator,
        {"hour": 3, "minute": 40},
    ),
    # Category drift is a slow signal (year-over-year quarterly compare);
    # monthly cadence is plenty.
    (
        "insights_category_drift",
        CategoryDriftGenerator,
        {"day": 1, "hour": 3, "minute": 50},
    ),
    # Year in money is a no-op except on Jan 1 + calendar-quarter mornings;
    # daily cadence lets the generator self-gate via `_period_bounds`.
    (
        "insights_year_in_money",
        YearInMoneyGenerator,
        {"hour": 4, "minute": 0},
    ),
)


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


def _make_insight_job(generator_cls: type[InsightGenerator]):  # type: ignore[no-untyped-def]
    """Build the async callable bound to a single generator class. Iterates
    every budget in the database; the orchestrator records its own InsightRun
    per generator per budget so a multi-budget user gets full observability."""

    async def job() -> None:
        settings = get_settings()
        async with async_session_maker() as session:
            budgets = await list_budgets_ordered(session)
            if not budgets:
                logger.info(
                    "scheduled %s skipped: no budgets present (run a sync first)",
                    generator_cls.card_type,
                )
                return
            for budget in budgets:
                outcome = await execute_generator(generator_cls, session, settings, budget.id)
                logger.info(
                    "scheduled %s for budget %s: status=%s created=%d updated=%d",
                    generator_cls.card_type,
                    budget.id,
                    outcome.status,
                    outcome.insights_created,
                    outcome.insights_updated,
                )

    job.__name__ = f"scheduled_{generator_cls.card_type}"
    return job


def build_scheduler() -> AsyncIOScheduler | None:
    """Return a configured scheduler, or None if scheduling is disabled."""
    settings = get_settings()
    if settings.sync_interval_minutes <= 0 and not settings.insights_generation_enabled:
        logger.info("scheduler disabled (sync interval <= 0 and insights off)")
        return None

    scheduler = AsyncIOScheduler()

    if settings.sync_interval_minutes > 0:
        scheduler.add_job(
            scheduled_sync,
            "interval",
            minutes=settings.sync_interval_minutes,
            id=JOB_ID,
            coalesce=True,
            max_instances=1,
        )

    if settings.insights_generation_enabled:
        for job_id, generator_cls, cron in _INSIGHT_JOBS:
            scheduler.add_job(
                _make_insight_job(generator_cls),
                "cron",
                id=job_id,
                coalesce=True,
                max_instances=1,
                **cron,
            )

    return scheduler
