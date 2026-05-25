"""ProxyHeaderMiddleware: warn-once-per-minute when X-Forwarded-Proto missing.

Note: this test attaches its own handler directly to the
`app.session.proxy_headers` logger instead of using pytest's `caplog`.
Reason: `app.main` calls `setup_logging()` at import time (triggered by
other tests in this suite). That clears root handlers and installs a
JSON formatter. `caplog` relies on a handler at the root, which the
global config can race with depending on test ordering. Attaching
directly bypasses the issue entirely.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.session import proxy_headers
from app.session.proxy_headers import ProxyHeaderMiddleware


class _ListHandler(logging.Handler):
    """Captures emitted records to an in-memory list. Test-only."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


@pytest_asyncio.fixture(autouse=True)
async def reset_warn_state() -> AsyncIterator[None]:
    """Per-test isolation for the module-level last-warn timestamps."""
    proxy_headers._LAST_WARN_AT.clear()
    yield
    proxy_headers._LAST_WARN_AT.clear()


@pytest_asyncio.fixture
async def captured() -> AsyncIterator[_ListHandler]:
    """Attach a fresh handler to the module logger and tear it down after.
    Independent of root-logger configuration `app.main.setup_logging` did."""
    handler = _ListHandler()
    logger = proxy_headers.logger
    logger.addHandler(handler)
    prior_level = logger.level
    logger.setLevel(logging.WARNING)
    try:
        yield handler
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prior_level)


def _make_app(require: bool) -> FastAPI:
    app = FastAPI()
    app.add_middleware(ProxyHeaderMiddleware, require_proxy_headers=require)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    return app


async def test_no_warning_when_disabled(captured: _ListHandler) -> None:
    app = _make_app(require=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/ping")
    assert r.status_code == 200
    assert not any("X-Forwarded-Proto" in rec.getMessage() for rec in captured.records)


async def test_no_warning_when_header_present(captured: _ListHandler) -> None:
    app = _make_app(require=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/ping", headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200
    assert not any("X-Forwarded-Proto" in rec.getMessage() for rec in captured.records)


async def test_warns_when_required_and_missing(captured: _ListHandler) -> None:
    app = _make_app(require=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/ping")
    assert r.status_code == 200
    matched = [rec for rec in captured.records if "X-Forwarded-Proto" in rec.getMessage()]
    assert len(matched) == 1


async def test_warning_throttled_within_window(captured: _ListHandler) -> None:
    app = _make_app(require=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        for _ in range(5):
            await ac.get("/ping")
    matched = [rec for rec in captured.records if "X-Forwarded-Proto" in rec.getMessage()]
    # First request warns; subsequent four within 60s are suppressed.
    assert len(matched) == 1
