import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import FastAPI

from app.routers import health, sync


def _run_migrations() -> None:
    config = Config("alembic.ini")
    command.upgrade(config, "head")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Alembic's env.py uses asyncio.run() internally, which fails from inside
    # a running event loop (uvicorn in prod, pytest-asyncio in tests). Pushing
    # the sync upgrade call to a worker thread sidesteps that.
    await asyncio.to_thread(_run_migrations)
    yield


app = FastAPI(title="ynab-insights", lifespan=lifespan)
app.include_router(health.router)
app.include_router(sync.router)
