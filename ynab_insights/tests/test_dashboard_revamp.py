"""Tests for the dashboard revamp: account groupings, date range picker,
charts data, and the monthly_outflows query helper."""

from datetime import UTC, date, datetime, timedelta

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Budget, Category, Payee, Transaction
from app.services.queries import _month_starts_back, monthly_outflows


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
            # One on-budget account, one tracking account
            Account(
                id="a-checking",
                budget_id="b-1",
                name="Checking",
                type="checking",
                balance_cents=125000,
                on_budget=True,
                closed=False,
            ),
            Account(
                id="a-401k",
                budget_id="b-1",
                name="401(K)",
                type="otherAsset",
                balance_cents=8000000,
                on_budget=False,
                closed=False,
            ),
            Category(
                id="c-rent", budget_id="b-1", category_group_id=None, name="Rent", hidden=False
            ),
            Payee(id="p-landlord", budget_id="b-1", name="Landlord", transfer_account_id=None),
            # One rent transaction this month, one 3 months ago
            Transaction(
                id="t-rent-now",
                budget_id="b-1",
                account_id="a-checking",
                category_id="c-rent",
                payee_id="p-landlord",
                date=today,
                amount_cents=-150000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-rent-old",
                budget_id="b-1",
                account_id="a-checking",
                category_id="c-rent",
                payee_id="p-landlord",
                date=today - timedelta(days=90),
                amount_cents=-145000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()
    return db_session


def test_month_starts_back_returns_n_months_oldest_first() -> None:
    months = _month_starts_back(date(2026, 5, 15), 3)
    assert months == [date(2026, 3, 1), date(2026, 4, 1), date(2026, 5, 1)]


def test_month_starts_back_wraps_year_boundary() -> None:
    months = _month_starts_back(date(2026, 2, 5), 4)
    assert months == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1), date(2026, 2, 1)]


async def test_monthly_outflows_returns_six_months_with_zero_for_empty(
    seeded: AsyncSession,
) -> None:
    result = await monthly_outflows(seeded, "b-1", months=6)
    assert len(result) == 6
    # Newest entry should include this month's rent (-150000)
    newest_month, newest_outflow = result[-1]
    today = date.today()
    assert newest_month == today.replace(day=1)
    assert newest_outflow == -150000
    # All entries are tuples of (date, int)
    for month, outflow in result:
        assert isinstance(month, date)
        assert isinstance(outflow, int)


async def test_dashboard_shows_on_budget_and_tracking_sections(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/")
    body = response.text
    assert "On-budget" in body
    assert "Tracking" in body
    # On-budget total = checking balance = 1250.00
    assert "$1,250.00" in body
    # Tracking total = 401k balance = 80,000.00
    assert "$80,000.00" in body
    # Both account names present
    assert "Checking" in body
    assert "401(K)" in body


async def test_dashboard_respects_date_range_query_params(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    today = date.today()
    older = today - timedelta(days=120)
    response = await client.get(
        "/",
        params={"date_from": older.isoformat(), "date_to": today.isoformat()},
    )
    body = response.text
    # The range should include the older rent transaction too,
    # so Rent total = 295000 cents = $2,950.00
    assert "$2,950.00" in body


async def test_dashboard_includes_chart_canvases(seeded: AsyncSession, client: AsyncClient) -> None:
    response = await client.get("/")
    body = response.text
    assert 'id="trend-chart"' in body
    assert 'id="category-donut"' in body
    # Chart.js script tag is loaded from CDN
    assert "chart.js" in body.lower() or "chart.umd.min.js" in body


async def test_dashboard_has_card_visibility_data_attributes(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    """The toggle JS keys off `data-card-id` and the `.card-body` wrapper."""
    response = await client.get("/")
    body = response.text
    for card_id in ["accounts", "trend", "categories", "ask", "recent"]:
        assert f'data-card-id="{card_id}"' in body
    assert "card-body" in body
