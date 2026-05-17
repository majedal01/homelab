"""Shared test setup.

Sets env vars before any app modules are imported so the cached Settings
picks up test values. Provides an async HTTP client fixture that runs the
FastAPI lifespan (migration runner) against an in-memory SQLite database.
"""
import os

os.environ.setdefault("APP_ENV", "stage")
os.environ.setdefault("APP_VERSION", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac
