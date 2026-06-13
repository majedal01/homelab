"""ProxyHeaderMiddleware: warn-once-per-minute when X-Forwarded-Proto missing.

The two "negative" tests (disabled + header-present) go through the HTTP
layer to verify the middleware is wired into the ASGI stack correctly.

The "positive" tests bypass HTTP and call `_maybe_warn` directly. The
observable is `_LAST_WARN_AT`, the module-level throttle dict the
middleware mutates. Dictionary state is unambiguous; log-record capture
isn't (the JSON formatter installed by setup_logging() at import time
races with caplog's root handler).

A previous round of these tests asserted log records and failed in CI
for what looked like multiple separate reasons. The actual underlying
cause was a bug in the middleware's throttle sentinel: `.get(key, 0.0)`
meant `now - 0.0 < 60` would suppress the FIRST warning on a fresh
container where `time.monotonic()` hadn't yet reached 60s. Fixed in
the same commit that introduced these tests; the dict-state assertion
catches a regression of that exact bug.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

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


def _bare_request(path: str = "/ping") -> Request:
    """A minimal ASGI Request with no proxy headers. Avoids the HTTP
    transport entirely so test-suite header injection can't hide the
    'missing header' case we want to exercise."""
    scope: dict[str, Any] = {
        "type": "http",
        "method": "GET",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    }
    return Request(scope)


async def _noop_asgi(scope: Any, receive: Any, send: Any) -> None:
    """Placeholder ASGI app. ProxyHeaderMiddleware.__init__ requires one
    but the unit tests below never call dispatch — they invoke
    `_maybe_warn` directly."""
    del scope, receive, send


# --- HTTP integration: verify middleware is wired (negative cases only) -----


async def test_no_warning_when_disabled() -> None:
    """Middleware disabled: no warning fires regardless of incoming headers."""
    app = _make_app(require=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/ping")
    assert r.status_code == 200
    assert proxy_headers._LAST_WARN_AT == {}


async def test_no_warning_when_header_present() -> None:
    """Middleware enabled but request has X-Forwarded-Proto: stays quiet."""
    app = _make_app(require=True)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        r = await ac.get("/ping", headers={"X-Forwarded-Proto": "https"})
    assert r.status_code == 200
    assert proxy_headers._LAST_WARN_AT == {}


# --- _maybe_warn unit tests: direct calls bypass the HTTP layer -------------


def test_maybe_warn_records_warning() -> None:
    """First call for a path records the timestamp."""
    mw = ProxyHeaderMiddleware(app=_noop_asgi, require_proxy_headers=True)
    mw._maybe_warn(_bare_request("/ping"))
    assert "/ping" in proxy_headers._LAST_WARN_AT


def test_maybe_warn_throttle_within_window() -> None:
    """Multiple calls in the same throttle window only update once."""
    mw = ProxyHeaderMiddleware(app=_noop_asgi, require_proxy_headers=True)
    req = _bare_request("/ping")
    mw._maybe_warn(req)
    first_ts = proxy_headers._LAST_WARN_AT["/ping"]
    for _ in range(4):
        mw._maybe_warn(req)
    # All 4 follow-ups within 60s: timestamp must not have advanced.
    assert proxy_headers._LAST_WARN_AT["/ping"] == first_ts


def test_maybe_warn_separate_paths_warn_independently() -> None:
    """The throttle is per-path, not global."""
    mw = ProxyHeaderMiddleware(app=_noop_asgi, require_proxy_headers=True)
    mw._maybe_warn(_bare_request("/ping"))
    mw._maybe_warn(_bare_request("/pong"))
    assert {"/ping", "/pong"} <= set(proxy_headers._LAST_WARN_AT.keys())
