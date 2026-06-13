"""Snapshot router smoke tests.

Drops a fake YnabSnapshot into the session and exercises each endpoint.
The router has no upstream calls, so no respx is needed; just a session
fixture that primes the in-memory store.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from app.session.middleware import SessionMiddleware  # noqa: F401  (force module init)
from app.session.models import UserSession
from app.session.store import COOKIE_NAME, get_session_store, new_sid
from app.snapshot.models import (
    Account,
    Category,
    Payee,
    Transaction,
    YnabSnapshot,
)


def _make_snapshot() -> YnabSnapshot:
    today = date.today()
    return YnabSnapshot(
        budget_id="b-1",
        budget_name="Test",
        currency_iso="USD",
        fetched_at=datetime.now(UTC),
        accounts=[
            Account(
                id="a-1",
                name="Checking",
                type="checking",
                on_budget=True,
                closed=False,
                balance_cents=500_00,
            ),
            Account(
                id="a-2",
                name="Savings",
                type="savings",
                on_budget=True,
                closed=False,
                balance_cents=2_500_00,
            ),
        ],
        categories=[
            Category(id="c-1", name="Groceries", hidden=False),
            Category(id="c-2", name="Inflow: Ready to Assign", hidden=False),
            Category(id="c-3", name="Hidden", hidden=True),
        ],
        payees=[Payee(id="p-1", name="Whole Foods")],
        transactions=[
            Transaction(
                id="t-1",
                date=today,
                amount_cents=-10_00,
                account_id="a-1",
                category_id="c-1",
                payee_id="p-1",
                memo="weekly",
            ),
            Transaction(
                id="t-2",
                date=today,
                amount_cents=3_000_00,
                account_id="a-1",
                category_id="c-2",  # income category
                payee_id=None,
            ),
        ],
    )


@pytest_asyncio.fixture
async def authed_client() -> AsyncIterator[AsyncClient]:
    """Spin up the app + a real session in the singleton store, hand the
    test a client with the signed cookie pre-attached."""
    from app.main import app

    store = get_session_store()
    session = UserSession(
        sid=new_sid(),
        ynab_token=SecretStr("0" * 64),
        anthropic_key=SecretStr("sk-ant-test"),
        budget_id="b-1",
        budget_name="Test",
        snapshot=_make_snapshot(),
    )
    store.create(session)
    signed = store.sign(session.sid)

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={COOKIE_NAME: signed},
        ) as ac:
            yield ac
    store.evict(session.sid)


async def test_list_accounts(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/snapshot/accounts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {a["name"] for a in body} == {"Checking", "Savings"}
    assert all("balance_cents" in a for a in body)


async def test_list_categories_skips_hidden(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/snapshot/categories")
    assert r.status_code == 200, r.text
    names = {c["name"] for c in r.json()}
    assert "Groceries" in names
    assert "Hidden" not in names
    # Groceries should reflect the one $10 outflow this month.
    groceries = next(c for c in r.json() if c["name"] == "Groceries")
    assert groceries["this_month_spend_cents"] == 1000


async def test_list_transactions_filters_compose(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/snapshot/transactions?category_id=c-1")
    assert r.status_code == 200
    body = r.json()
    assert [t["id"] for t in body] == ["t-1"]
    assert body[0]["payee_name"] == "Whole Foods"


async def test_list_transactions_payee_substring(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/snapshot/transactions?payee_contains=whole")
    assert r.status_code == 200
    assert [t["id"] for t in r.json()] == ["t-1"]


async def test_summary_uses_period_summary_semantics(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/snapshot/summary")
    assert r.status_code == 200
    body = r.json()
    # Income: $3,000 inflow. Spending: $10 outflow. Net: $2,990.
    assert body["income_cents"] == 300_000
    assert body["spending_cents"] == 1_000
    assert body["net_income_cents"] == 299_000


async def test_monthly_trend_returns_requested_months(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/snapshot/monthly-trend?months=3")
    assert r.status_code == 200
    points = r.json()["points"]
    assert len(points) == 3
    # The most recent month carries our seeded transactions.
    last = points[-1]
    assert last["income_cents"] == 300_000
    assert last["spending_cents"] == 1_000


async def test_overview_kpis(authed_client: AsyncClient) -> None:
    r = await authed_client.get("/api/snapshot/overview")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["net_worth_cents"] == 500_00 + 2_500_00
    assert body["this_month_income_cents"] == 300_000
    assert body["this_month_spending_cents"] == 1_000
    assert body["transaction_count"] == 2


async def test_endpoints_401_without_cookie() -> None:
    from app.main import app

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            r = await ac.get("/api/snapshot/accounts")
            assert r.status_code == 401


async def test_endpoints_409_without_budget(authed_client: AsyncClient) -> None:
    """A session without a snapshot should 409, not 200 with empty data."""
    # Fetch the actual session out of the store and clear its snapshot.
    store = get_session_store()
    sid = authed_client.cookies[COOKIE_NAME]
    # Cookie value is signed; unsign to get the real sid.
    real_sid = store.unsign(sid)
    assert real_sid is not None
    session = store.get(real_sid)
    assert session is not None
    session.snapshot = None

    r = await authed_client.get("/api/snapshot/accounts")
    assert r.status_code == 409
