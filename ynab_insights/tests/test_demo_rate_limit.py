"""Rate limit on POST /api/session/demo.

Builds a minimal FastAPI app with the real RateLimitMiddleware tuned to a
small limit, so the test trips it without making thousands of requests.
The middleware reads `_rules` at __init__ time, so a fresh Settings + a
fresh middleware instance is the cleanest isolation.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.session.rate_limit import RateLimitMiddleware


def _settings(demo_limit: int) -> Settings:
    """Build a Settings with a tiny demo limit, defaults elsewhere."""
    return Settings(
        app_env="stage",
        app_version="test",
        session_secret_key="test",
        demo_session_rate_limit_per_ip_per_hour=demo_limit,
    )


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, settings=_settings(demo_limit=3))

    # Stub the endpoint at the same path so the rate-limit rule matches.
    @app.post("/api/session/demo")
    async def fake_demo() -> dict[str, bool]:
        return {"ok": True}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


async def test_demo_endpoint_within_limit_succeeds(client: AsyncClient) -> None:
    for _ in range(3):
        r = await client.post("/api/session/demo")
        assert r.status_code == 200, r.text


async def test_demo_endpoint_429_after_limit(client: AsyncClient) -> None:
    for _ in range(3):
        assert (await client.post("/api/session/demo")).status_code == 200
    r = await client.post("/api/session/demo")
    assert r.status_code == 429, r.text
    body = r.json()
    assert body["error"] == "rate_limited"
    assert body["scope"] == "demo_session_create"
    assert isinstance(body["retry_after_seconds"], int)
    assert body["retry_after_seconds"] >= 1
    assert r.headers.get("Retry-After") is not None
