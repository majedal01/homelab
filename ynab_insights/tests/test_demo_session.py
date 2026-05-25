"""Demo session smoke tests."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.session.store import COOKIE_NAME


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


async def test_create_demo_session_no_payload(client: AsyncClient) -> None:
    r = await client.post("/api/session/demo")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_demo"] is True
    assert body["budget_id"] == "demo-budget"
    assert body["budget_name"] == "Demo Budget"
    assert COOKIE_NAME in r.cookies


async def test_demo_session_lists_pre_baked_insights(client: AsyncClient) -> None:
    await client.post("/api/session/demo")
    r = await client.get("/api/insights")
    assert r.status_code == 200, r.text
    insights = r.json()
    # One insight per card type ships baked in.
    assert len(insights) == 6
    card_types = {i["card_type"] for i in insights}
    assert card_types == {
        "subscription_audit",
        "spending_anomaly",
        "cashflow_forecast",
        "goal_trajectory",
        "category_drift",
        "year_in_money",
    }
    # All should be flagged as not LLM-enhanced (hand-written fallback copy).
    assert all(not i["llm_enhanced"] for i in insights)


async def test_demo_session_explore_endpoints_work(client: AsyncClient) -> None:
    await client.post("/api/session/demo")
    accounts = (await client.get("/api/snapshot/accounts")).json()
    assert any(a["name"] == "Checking" for a in accounts)
    cats = (await client.get("/api/snapshot/categories")).json()
    assert any(c["name"] == "Vacation Fund" for c in cats)


async def test_demo_ask_is_forbidden(client: AsyncClient) -> None:
    await client.post("/api/session/demo")
    r = await client.post(
        "/ask",
        json={"question": "What did I spend on groceries?", "history": []},
    )
    assert r.status_code == 403
    body = r.json()
    assert body["detail"]["error"] == "demo_mode_ask_disabled"


async def test_demo_generate_returns_empty_run_list(client: AsyncClient) -> None:
    """Hitting Regenerate in demo mode should silently no-op."""
    await client.post("/api/session/demo")
    r = await client.post("/api/insights/generate")
    assert r.status_code == 200
    assert r.json() == {"run_ids": []}


async def test_demo_refresh_bumps_active_at_only(client: AsyncClient) -> None:
    await client.post("/api/session/demo")
    r = await client.post("/api/session/refresh")
    assert r.status_code == 200
    assert r.json()["is_demo"] is True
