"""Tests for the category drill-down page, its HTMX filter partial, and the
link from the dashboard."""

from datetime import UTC, date, datetime, timedelta

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Budget, Category, Payee, Transaction


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    today = date.today()
    db_session.add_all(
        [
            Budget(
                id="b-1",
                name="Main",
                currency="USD",
                last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
            ),
            Account(
                id="a-1",
                budget_id="b-1",
                name="Checking",
                type="checking",
                balance_cents=10000,
                on_budget=True,
                closed=False,
            ),
            Category(id="c-1", budget_id="b-1", category_group_id=None, name="Rent", hidden=False),
            Payee(id="p-1", budget_id="b-1", name="Landlord", transfer_account_id=None),
            # Three rent transactions: today, 15 days ago, 200 days ago
            Transaction(
                id="t-now",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-1",
                payee_id="p-1",
                date=today,
                amount_cents=-150000,
                memo="this month",
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-recent",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-1",
                payee_id="p-1",
                date=today - timedelta(days=15),
                amount_cents=-150000,
                memo="last month",
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-old",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-1",
                payee_id="p-1",
                date=today - timedelta(days=200),
                amount_cents=-99900,
                memo="ancient",
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()
    return db_session


async def test_category_detail_returns_html(seeded: AsyncSession, client: AsyncClient) -> None:
    response = await client.get("/categories/c-1")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "Rent" in response.text


async def test_category_detail_defaults_to_current_month(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/categories/c-1")
    body = response.text
    # Only today's transaction is in the current calendar month
    assert "this month" in body
    # Last month and ancient transactions should be excluded
    assert "ancient" not in body


async def test_category_detail_custom_date_range_includes_more(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    today = date.today()
    from_date = (today - timedelta(days=30)).isoformat()
    to_date = today.isoformat()
    response = await client.get(
        "/categories/c-1", params={"date_from": from_date, "date_to": to_date}
    )
    body = response.text
    assert "this month" in body
    assert "last month" in body
    assert "ancient" not in body


async def test_category_detail_404_for_missing_category(client: AsyncClient) -> None:
    response = await client.get("/categories/does-not-exist")
    assert response.status_code == 404


async def test_partial_category_transactions_returns_fragment(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    today = date.today()
    response = await client.get(
        "/_partials/category_transactions",
        params={
            "category_id": "c-1",
            "date_from": (today - timedelta(days=30)).isoformat(),
            "date_to": today.isoformat(),
        },
    )
    assert response.status_code == 200
    body = response.text
    assert "<html" not in body  # fragment, no full page wrapper
    assert "this month" in body
    assert "last month" in body


async def test_dashboard_links_to_category_drill_down(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/")
    body = response.text
    assert 'href="/categories/c-1"' in body
