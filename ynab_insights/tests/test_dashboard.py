"""End-to-end tests for the HTML dashboard. Seeds via db_session, hits routes
via client, asserts on rendered HTML content (string contains, not full DOM)."""

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
                balance_cents=125000,
                on_budget=True,
                closed=False,
            ),
            Account(
                id="a-closed",
                budget_id="b-1",
                name="Old Savings",
                type="savings",
                balance_cents=0,
                on_budget=True,
                closed=True,
            ),
            Category(id="c-1", budget_id="b-1", category_group_id=None, name="Rent", hidden=False),
            Category(
                id="c-2", budget_id="b-1", category_group_id=None, name="Groceries", hidden=False
            ),
            Payee(id="p-1", budget_id="b-1", name="Landlord", transfer_account_id=None),
            # Two transactions this month: rent (-150000) and groceries (-20000)
            Transaction(
                id="t-1",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-1",
                payee_id="p-1",
                date=today,
                amount_cents=-150000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-2",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-2",
                payee_id="p-1",
                date=today,
                amount_cents=-20000,
                memo="weekly",
                cleared="cleared",
                approved=True,
            ),
            # Old transaction outside the current month -- shouldn't affect monthly totals
            Transaction(
                id="t-old",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-1",
                payee_id="p-1",
                date=today - timedelta(days=120),
                amount_cents=-99900,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()
    return db_session


async def test_dashboard_returns_html(seeded: AsyncSession, client: AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "YNAB Insights" in response.text


async def test_dashboard_shows_open_accounts_only(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/")
    body = response.text
    assert "Checking" in body
    assert "$1,250.00" in body  # 125000 / 100, with comma
    assert "Old Savings" not in body  # closed account excluded


async def test_dashboard_aggregates_current_month_spending(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/")
    body = response.text
    # Rent shows first (largest spend), groceries second
    rent_pos = body.find("Rent")
    groc_pos = body.find("Groceries")
    assert rent_pos != -1 and groc_pos != -1
    assert rent_pos < groc_pos
    # Old transaction is NOT in this month's totals: it would add another 99900 to Rent
    assert "$1,500.00" in body  # rent this month only
    assert "$200.00" in body  # groceries
    # If old txn leaked in, we'd see $2,499.00 for rent
    assert "$2,499.00" not in body


async def test_dashboard_lists_recent_transactions(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/")
    body = response.text
    # Both recent transactions should appear
    assert "Landlord" in body
    assert "weekly" in body  # memo from the groceries txn


async def test_partial_transactions_returns_fragment(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/_partials/transactions", params={"budget_id": "b-1"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    # Fragment doesn't include <html> or <body> tags
    assert "<html" not in response.text
    assert "Landlord" in response.text


async def test_dashboard_empty_state(client: AsyncClient) -> None:
    """No budgets seeded -- empty state renders without crashing."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "No budgets yet" in response.text


async def test_dashboard_switches_budget_via_query_param(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    # Add a second budget so the picker has a choice
    seeded.add(
        Budget(
            id="b-2",
            name="Other",
            currency="USD",
            last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    await seeded.commit()
    response = await client.get("/", params={"budget_id": "b-2"})
    assert response.status_code == 200
    # Selected attribute should land on b-2
    assert 'value="b-2" selected' in response.text
