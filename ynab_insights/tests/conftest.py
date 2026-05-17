"""Shared test setup.

Sets env vars before any app modules are imported so the cached Settings
picks up test values. Provides a shared in-memory SQLite engine that both
the FastAPI app (via dependency override) and tests (via `db_session`) use,
so seeded data is visible to the routes under test.
"""

import os

os.environ.setdefault("APP_ENV", "stage")
os.environ.setdefault("APP_VERSION", "test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

from collections.abc import AsyncIterator  # noqa: E402

import pytest_asyncio  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402


@pytest_asyncio.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite engine shared between the app and the test session.
    StaticPool keeps the same underlying connection so all queries see the
    same in-memory database."""
    from app.db import Base

    eng = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Seeded session for tests that need to insert data before hitting the API."""
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    """Async HTTP client wired to the FastAPI app, with `get_session` overridden
    to use the same in-memory engine as `db_session`."""
    from app.db import get_session
    from app.main import app

    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override_get_session() -> AsyncIterator[AsyncSession]:
        async with maker() as session:
            yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        async with LifespanManager(app):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as ac:
                yield ac
    finally:
        app.dependency_overrides.clear()
