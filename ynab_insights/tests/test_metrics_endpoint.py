"""/metrics endpoint: gated by X-Admin-Token against METRICS_ADMIN_TOKEN env."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


async def test_metrics_404_when_token_env_unset(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The endpoint is invisible to scanners when the operator hasn't
    enabled it. Empty METRICS_ADMIN_TOKEN -> 404 regardless of header."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "metrics_admin_token", "")

    r = await client.get("/metrics")
    assert r.status_code == 404

    r = await client.get("/metrics", headers={"X-Admin-Token": "anything"})
    assert r.status_code == 404


async def test_metrics_404_when_token_wrong(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Wrong token -> same 404 as the unset case (no info leak)."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "metrics_admin_token", "the-real-token")

    r = await client.get("/metrics", headers={"X-Admin-Token": "guess"})
    assert r.status_code == 404

    r = await client.get("/metrics")  # missing header
    assert r.status_code == 404


async def test_metrics_returns_prometheus_text_when_authed(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "metrics_admin_token", "letmein")

    r = await client.get("/metrics", headers={"X-Admin-Token": "letmein"})
    assert r.status_code == 200
    # Prometheus text exposition format starts with HELP / TYPE lines.
    body = r.text
    assert "# HELP" in body
    assert "# TYPE" in body
    # Spot-check one of the metrics we defined.
    assert "sessions_created_total" in body
