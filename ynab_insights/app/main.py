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
    _run_migrations()
    yield


app = FastAPI(title="ynab-insights", lifespan=lifespan)
app.include_router(health.router)
app.include_router(sync.router)
