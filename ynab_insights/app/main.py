import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI

from app import insights as _insights  # noqa: F401  side-effect: registers generators
from app.config import get_settings
from app.logging_config import setup_logging
from app.routers import (
    accounts,
    ask,
    budgets,
    categories,
    health,
    insights,
    metrics,
    payees,
    reports,
    suggestions,
    sync,
    transactions,
)
from app.routers import (
    session as session_router,
)
from app.services.scheduler import build_scheduler
from app.session import SessionMiddleware, get_session_store

setup_logging(get_settings().app_env)


def _run_migrations() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Skip Alembic in tests (sqlite). Tests build the schema via
    # Base.metadata.create_all on a shared in-memory engine so they can seed
    # data and have it visible to the routes.
    if not get_settings().database_url.startswith("sqlite"):
        # Alembic's env.py uses asyncio.run() internally, which fails from inside
        # a running event loop (uvicorn in prod). Push to a worker thread to
        # sidestep that.
        await asyncio.to_thread(_run_migrations)

    scheduler = build_scheduler()
    if scheduler is not None:
        scheduler.start()
    try:
        yield
    finally:
        if scheduler is not None:
            scheduler.shutdown(wait=False)


app = FastAPI(title="ynab-insights", lifespan=lifespan)
app.add_middleware(SessionMiddleware, store=get_session_store())
app.include_router(health.router)
app.include_router(sync.router)
app.include_router(budgets.router)
app.include_router(accounts.router)
app.include_router(categories.router)
app.include_router(payees.router)
app.include_router(transactions.router)
app.include_router(ask.router)
app.include_router(suggestions.router)
app.include_router(insights.router)
app.include_router(reports.router)
app.include_router(metrics.router)
app.include_router(session_router.router)
