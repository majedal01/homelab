"""End-to-end tests for the read API. Each test seeds via `db_session` and
queries via `client`; both share the same in-memory SQLite engine."""

from datetime import UTC, date, datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Budget, Category, Payee, Transaction


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    """Two budgets, accounts under each, a mix of categories/payees/transactions
    to exercise filters and the embedded-name response shape."""
    db_session.add_all(
        [
            Budget(
                id="b-1",
                name="Main",
                currency="USD",
                last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
            ),
            Budget(
                id="b-2",
                name="Business",
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
            Account(
                id="a-2",
                budget_id="b-1",
                name="Closed Savings",
                type="savings",
                balance_cents=0,
                on_budget=True,
                closed=True,
            ),
            Account(
                id="a-3",
                budget_id="b-2",
                name="Biz Checking",
                type="checking",
                balance_cents=50000,
                on_budget=True,
                closed=False,
            ),
            Category(id="c-1", budget_id="b-1", category_group_id=None, name="Rent", hidden=False),
            Category(
                id="c-2",
                budget_id="b-1",
                category_group_id=None,
                name="Old Subscription",
                hidden=True,
            ),
            Category(
                id="c-3", budget_id="b-2", category_group_id=None, name="Office", hidden=False
            ),
            Payee(id="p-1", budget_id="b-1", name="Landlord", transfer_account_id=None),
            Payee(id="p-2", budget_id="b-2", name="WeWork", transfer_account_id=None),
            Transaction(
                id="t-1",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-1",
                payee_id="p-1",
                date=date(2026, 5, 1),
                amount_cents=-150000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-2",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-1",
                payee_id="p-1",
                date=date(2026, 4, 1),
                amount_cents=-150000,
                memo="april rent",
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-3",
                budget_id="b-1",
                account_id="a-1",
                category_id=None,
                payee_id=None,
                date=date(2026, 3, 15),
                amount_cents=-5000,
                memo="cash",
                cleared="uncleared",
                approved=False,
            ),
            Transaction(
                id="t-4",
                budget_id="b-2",
                account_id="a-3",
                category_id="c-3",
                payee_id="p-2",
                date=date(2026, 5, 5),
                amount_cents=-25000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()
    return db_session


async def test_list_budgets_returns_seeded_budgets(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/budgets")
    assert response.status_code == 200
    names = [b["name"] for b in response.json()]
    assert names == ["Business", "Main"]


async def test_list_accounts_filters_by_budget(seeded: AsyncSession, client: AsyncClient) -> None:
    response = await client.get("/accounts", params={"budget_id": "b-1"})
    assert response.status_code == 200
    assert {a["id"] for a in response.json()} == {"a-1", "a-2"}


async def test_list_accounts_excludes_closed_when_requested(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/accounts", params={"budget_id": "b-1", "include_closed": "false"})
    assert response.status_code == 200
    ids = {a["id"] for a in response.json()}
    assert ids == {"a-1"}


async def test_list_categories_excludes_hidden_when_requested(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get(
        "/categories", params={"budget_id": "b-1", "include_hidden": "false"}
    )
    assert response.status_code == 200
    ids = {c["id"] for c in response.json()}
    assert ids == {"c-1"}


async def test_list_payees_filters_by_budget(seeded: AsyncSession, client: AsyncClient) -> None:
    response = await client.get("/payees", params={"budget_id": "b-2"})
    assert response.status_code == 200
    payees = response.json()
    assert len(payees) == 1
    assert payees[0]["name"] == "WeWork"


async def test_list_transactions_embeds_names(seeded: AsyncSession, client: AsyncClient) -> None:
    response = await client.get("/transactions", params={"budget_id": "b-1"})
    assert response.status_code == 200
    rows = response.json()
    # Sorted by date desc, id desc
    assert [r["id"] for r in rows] == ["t-1", "t-2", "t-3"]
    # First two have rent + landlord embedded
    assert rows[0]["account_name"] == "Checking"
    assert rows[0]["category_name"] == "Rent"
    assert rows[0]["payee_name"] == "Landlord"
    # Third has null category and payee but account name is still populated
    assert rows[2]["account_name"] == "Checking"
    assert rows[2]["category_name"] is None
    assert rows[2]["payee_name"] is None


async def test_list_transactions_filters_by_date_range(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get(
        "/transactions",
        params={"budget_id": "b-1", "date_from": "2026-04-01", "date_to": "2026-04-30"},
    )
    assert response.status_code == 200
    rows = response.json()
    assert [r["id"] for r in rows] == ["t-2"]


async def test_list_transactions_filters_by_category(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/transactions", params={"category_id": "c-3"})
    assert response.status_code == 200
    rows = response.json()
    assert [r["id"] for r in rows] == ["t-4"]


async def test_list_transactions_pagination(seeded: AsyncSession, client: AsyncClient) -> None:
    page1 = await client.get("/transactions", params={"budget_id": "b-1", "limit": 2, "offset": 0})
    page2 = await client.get("/transactions", params={"budget_id": "b-1", "limit": 2, "offset": 2})
    page1_ids = [r["id"] for r in page1.json()]
    page2_ids = [r["id"] for r in page2.json()]
    assert page1_ids == ["t-1", "t-2"]
    assert page2_ids == ["t-3"]


async def test_list_transactions_rejects_invalid_limit(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/transactions", params={"limit": 9999})
    assert response.status_code == 422
