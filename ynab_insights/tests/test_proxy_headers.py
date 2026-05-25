"""ProxyHeaderMiddleware: warn-once-per-minute when X-Forwarded-Proto missing."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.session import proxy_headers
from app.session.proxy_headers import ProxyHeaderMiddleware


@pytest_asyncio.fixture(autouse=True)
async def reset_warn_state() -> AsyncIterator[None]:
    """Per-test isolation for the module-level last-warn timestamps."""
    proxy_headers._LAST_WARN_AT.clear()
    yield
    proxy_headers._LAST_WARN_AT.clear()


def _make_app(require: bool) -> FastAPI:
    app = FastAPI()
    app.add_middleware(ProxyHeaderMiddleware, require_proxy_headers=require)

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"ok": "yes"}

    return app


async def test_no_warning_when_disabled(caplog: pytest.LogCaptureFixture) -> None:
    app = _make_app(require=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with caplog.at_level(logging.WARNING, logger="app.session.proxy_headers"):
            r = await ac.get("/ping")
    assert r.status_code == 200
    assert not any("X-Forwarded-Proto" in rec.message for rec in caplog.records)


async def test_no_warning_when_header_present(caplog: pytest.LogCaptureFixture) -> None:
    app = _make_app(require=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with caplog.at_level(logging.WARNING, logger="app.session.proxy_headers"):
            r = await ac.get("/ping", headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200
    assert not any("X-Forwarded-Proto" in rec.message for rec in caplog.records)


async def test_warns_when_required_and_missing(caplog: pytest.LogCaptureFixture) -> None:
    app = _make_app(require=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with caplog.at_level(logging.WARNING, logger="app.session.proxy_headers"):
            r = await ac.get("/ping")
    assert r.status_code == 200
    msgs = [rec.message for rec in caplog.records if "X-Forwarded-Proto" in rec.message]
    assert len(msgs) == 1


async def test_warning_throttled_within_window(caplog: pytest.LogCaptureFixture) -> None:
    app = _make_app(require=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        with caplog.at_level(logging.WARNING, logger="app.session.proxy_headers"):
            for _ in range(5):
                await ac.get("/ping")
    msgs = [rec.message for rec in caplog.records if "X-Forwarded-Proto" in rec.message]
    # First request warns; subsequent four within 60s are suppressed.
    assert len(msgs) == 1
