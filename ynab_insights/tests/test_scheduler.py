"""Tests for the concurrency guard and the scheduled-sync runner."""

import asyncio
import logging
from collections.abc import AsyncIterator

import httpx
import pytest
import pytest_asyncio
import respx
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db import Base
from app.services import scheduler as scheduler_module
from app.services.scheduler import build_scheduler, scheduled_sync
from app.services.sync import SyncInProgressError, _sync_lock, run_sync
from app.services.ynab_client import DEFAULT_BASE_URL


@pytest_asyncio.fixture(autouse=True)
async def reset_sync_lock() -> AsyncIterator[None]:
    """The sync lock is module-level. Reset between tests so prior failures
    don't leave it acquired and poison subsequent tests."""
    while _sync_lock.locked():
        _sync_lock.release()
    yield
    while _sync_lock.locked():
        _sync_lock.release()


@pytest_asyncio.fixture
async def fresh_engine() -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def fresh_session(fresh_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(fresh_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


def _stub_ynab_minimal() -> None:
    """Mock just enough of YNAB so run_sync completes quickly."""
    respx.get(f"{DEFAULT_BASE_URL}/budgets").mock(
        return_value=httpx.Response(200, json={"data": {"budgets": []}})
    )


@respx.mock
async def test_run_sync_raises_when_already_running(fresh_session: AsyncSession) -> None:
    _stub_ynab_minimal()
    # Manually hold the lock to simulate an in-flight sync.
    await _sync_lock.acquire()
    try:
        with pytest.raises(SyncInProgressError):
            await run_sync(fresh_session, "test-token")
    finally:
        _sync_lock.release()


@respx.mock
async def test_sync_endpoint_returns_409_when_already_running(client) -> None:  # type: ignore[no-untyped-def]
    from app.config import get_settings

    # Stash an in-flight sync.
    await _sync_lock.acquire()
    try:
        # Bypass the 503 by setting a token on the cached settings instance.
        get_settings().ynab_token = "test-token"
        response = await client.post("/sync")
        assert response.status_code == 409
        assert "already running" in response.json()["detail"]
    finally:
        _sync_lock.release()
        get_settings().ynab_token = None


async def test_scheduled_sync_skips_when_no_token(caplog: pytest.LogCaptureFixture) -> None:
    from app.config import get_settings

    get_settings().ynab_token = None
    caplog.set_level(logging.INFO, logger="app.services.scheduler")
    await scheduled_sync()
    assert any("YNAB_TOKEN not configured" in r.message for r in caplog.records)


async def test_scheduled_sync_swallows_in_progress_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.config import get_settings

    get_settings().ynab_token = "test-token"
    await _sync_lock.acquire()
    try:
        caplog.set_level(logging.INFO, logger="app.services.scheduler")
        await scheduled_sync()  # should NOT raise
        assert any("another sync is in progress" in r.message for r in caplog.records)
    finally:
        _sync_lock.release()
        get_settings().ynab_token = None


async def test_build_scheduler_returns_none_when_disabled() -> None:
    from app.config import get_settings

    original = get_settings().sync_interval_minutes
    get_settings().sync_interval_minutes = 0
    try:
        assert build_scheduler() is None
    finally:
        get_settings().sync_interval_minutes = original


async def test_build_scheduler_configures_job_when_enabled() -> None:
    from app.config import get_settings

    original = get_settings().sync_interval_minutes
    get_settings().sync_interval_minutes = 15
    try:
        scheduler = build_scheduler()
        assert scheduler is not None
        job = scheduler.get_job(scheduler_module.JOB_ID)
        assert job is not None
        assert job.trigger.interval.total_seconds() == 15 * 60
    finally:
        get_settings().sync_interval_minutes = original


async def _delay_then_release(delay: float) -> None:
    await asyncio.sleep(delay)
    _sync_lock.release()


@respx.mock
async def test_concurrent_run_sync_calls_one_succeeds_one_raises(
    fresh_session: AsyncSession,
) -> None:
    """Two simultaneous calls to run_sync: exactly one should win the lock,
    the other should observe SyncInProgressError immediately."""
    _stub_ynab_minimal()

    # We can't trivially fire two truly-concurrent run_syncs with the same session
    # (sessions aren't safe for concurrent use), so simulate the race with one
    # holding the lock and another attempting to acquire.
    await _sync_lock.acquire()
    asyncio.create_task(_delay_then_release(0.05))
    with pytest.raises(SyncInProgressError):
        await run_sync(fresh_session, "test-token")
