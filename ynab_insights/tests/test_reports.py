"""Tests for the aggregated /reports endpoints."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Budget, Payee, Transaction


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    """Seed one budget, two accounts (one on-budget, one tracking), and a
    spread of transactions across the current and prior months so the
    aggregate query has signal to roll up."""
    today = date.today()
    last_month = (
        date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
    )

    db_session.add(
        Budget(
            id="b-1",
            name="Main",
            currency="USD",
            last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    db_session.add(
        Account(
            id="a-tracking",
            budget_id="b-1",
            name="Investment",
            type="otherAsset",
            balance_cents=0,
            on_budget=False,
            closed=False,
        )
    )
    db_session.add(Payee(id="p-1", budget_id="b-1", name="Vendor"))
    # Transfer payee so we can verify exclusion.
    db_session.add(
        Payee(
            id="p-xfer",
            budget_id="b-1",
            name="Transfer",
            transfer_account_id="a-tracking",
        )
    )
    db_session.add_all(
        [
            # On-budget spending this month: $100
            Transaction(
                id="t-this-spend",
                budget_id="b-1",
                account_id="a-1",
                category_id=None,
                payee_id="p-1",
                date=date(today.year, today.month, 1),
                amount_cents=-10000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            # On-budget income this month: $500
            Transaction(
                id="t-this-income",
                budget_id="b-1",
                account_id="a-1",
                category_id=None,
                payee_id="p-1",
                date=date(today.year, today.month, 1),
                amount_cents=50000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            # On-budget spending last month: $200
            Transaction(
                id="t-last-spend",
                budget_id="b-1",
                account_id="a-1",
                category_id=None,
                payee_id="p-1",
                date=last_month,
                amount_cents=-20000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            # Transfer should be excluded
            Transaction(
                id="t-xfer",
                budget_id="b-1",
                account_id="a-1",
                category_id=None,
                payee_id="p-xfer",
                date=date(today.year, today.month, 5),
                amount_cents=-50000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            # Tracking-account transaction should be excluded (off-budget)
            Transaction(
                id="t-tracking",
                budget_id="b-1",
                account_id="a-tracking",
                category_id=None,
                payee_id="p-1",
                date=date(today.year, today.month, 7),
                amount_cents=-99999,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()
    return db_session


async def test_monthly_spending_aggregates_on_budget_only(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    today = date.today()
    response = await client.get(
        "/reports/monthly-spending",
        params={"budget_id": "b-1", "months": 3},
    )
    assert response.status_code == 200
    points = response.json()["points"]
    assert len(points) == 3
    by_ym = {(p["year"], p["month"]): p for p in points}

    current = by_ym[(today.year, today.month)]
    assert current["spending_cents"] == 10000  # transfer + tracking excluded
    assert current["income_cents"] == 50000

    last_month = (
        date(today.year - 1, 12, 1) if today.month == 1 else date(today.year, today.month - 1, 1)
    )
    last = by_ym[(last_month.year, last_month.month)]
    assert last["spending_cents"] == 20000
    assert last["income_cents"] == 0


async def test_monthly_spending_requires_budget_id(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/reports/monthly-spending", params={"months": 6})
    assert response.status_code == 422


async def test_monthly_spending_rejects_out_of_range_months(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get(
        "/reports/monthly-spending", params={"budget_id": "b-1", "months": 999}
    )
    assert response.status_code == 422
