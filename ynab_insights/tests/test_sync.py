"""End-to-end test of the sync orchestrator against a fresh SQLite database
with the YNAB API mocked via respx."""

from collections.abc import AsyncIterator

import httpx
import pytest_asyncio
import respx
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.db import Base
from app.models import Account, Budget, Transaction
from app.services.sync import run_sync
from app.services.ynab_client import DEFAULT_BASE_URL


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as s:
        yield s
    await engine.dispose()


def _mock_ynab() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/budgets").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "budgets": [
                        {
                            "id": "b-1",
                            "name": "Main",
                            "currency_format": {"iso_code": "USD"},
                            "last_modified_on": "2026-05-15T00:00:00+00:00",
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "accounts": [
                        {
                            "id": "a-1",
                            "name": "Checking",
                            "type": "checking",
                            "balance": 100000,
                            "on_budget": True,
                            "closed": False,
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/categories").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "category_groups": [
                        {
                            "id": "cg-1",
                            "name": "Bills",
                            "categories": [
                                {
                                    "id": "c-1",
                                    "category_group_id": "cg-1",
                                    "name": "Rent",
                                    "hidden": False,
                                }
                            ],
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/payees").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"payees": [{"id": "p-1", "name": "Landlord"}]}},
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "transactions": [
                        {
                            "id": "t-1",
                            "account_id": "a-1",
                            "category_id": "c-1",
                            "payee_id": "p-1",
                            "date": "2026-05-01",
                            "amount": -1500000,
                            "memo": None,
                            "cleared": "cleared",
                            "approved": True,
                        }
                    ]
                }
            },
        )
    )


@respx.mock
async def test_run_sync_persists_each_entity_type(session: AsyncSession) -> None:
    _mock_ynab()
    result = await run_sync(session, "test-token")
    assert result.budgets == 1
    assert result.accounts == 1
    assert result.categories == 1
    assert result.payees == 1
    assert result.transactions == 1

    budget = await session.get(Budget, "b-1")
    assert budget is not None
    assert budget.name == "Main"
    assert budget.currency == "USD"

    account = await session.get(Account, "a-1")
    assert account is not None
    assert account.balance_cents == 10000  # 100000 milliunits / 10

    txn = await session.get(Transaction, "t-1")
    assert txn is not None
    assert txn.amount_cents == -150000  # -1500000 / 10


@respx.mock
async def test_run_sync_is_idempotent(session: AsyncSession) -> None:
    _mock_ynab()
    first = await run_sync(session, "test-token")
    second = await run_sync(session, "test-token")
    assert first.transactions == second.transactions == 1

    txns = (await session.execute(Transaction.__table__.select())).all()
    assert len(txns) == 1


@respx.mock
async def test_run_sync_nullifies_orphan_category_and_payee_refs(
    session: AsyncSession,
) -> None:
    """Transactions whose category or payee was deleted in YNAB should still
    persist, with the orphan FK set to NULL."""
    respx.get(f"{DEFAULT_BASE_URL}/budgets").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "budgets": [
                        {
                            "id": "b-1",
                            "name": "Main",
                            "currency_format": {"iso_code": "USD"},
                            "last_modified_on": "2026-05-15T00:00:00+00:00",
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "accounts": [
                        {
                            "id": "a-1",
                            "name": "Checking",
                            "type": "checking",
                            "balance": 0,
                            "on_budget": True,
                            "closed": False,
                        }
                    ]
                }
            },
        )
    )
    # YNAB returns NO categories and NO payees (e.g. they were all deleted).
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/categories").mock(
        return_value=httpx.Response(200, json={"data": {"category_groups": []}})
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/payees").mock(
        return_value=httpx.Response(200, json={"data": {"payees": []}})
    )
    # Transaction references a category and a payee that no longer exist.
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "transactions": [
                        {
                            "id": "t-orphan",
                            "account_id": "a-1",
                            "category_id": "c-deleted",
                            "payee_id": "p-deleted",
                            "date": "2022-07-31",
                            "amount": -132000,
                            "memo": "",
                            "cleared": "reconciled",
                            "approved": True,
                        }
                    ]
                }
            },
        )
    )

    result = await run_sync(session, "test-token")
    assert result.transactions == 1

    txn = await session.get(Transaction, "t-orphan")
    assert txn is not None
    assert txn.category_id is None
    assert txn.payee_id is None
    assert txn.account_id == "a-1"
    assert txn.amount_cents == -13200


@respx.mock
async def test_run_sync_expands_split_transaction_subs(session: AsyncSession) -> None:
    """A split transaction's parent has category_id=null and the full amount;
    each subtransaction carries its own category. The sync should persist one
    Transaction row per leg, not the parent."""
    respx.get(f"{DEFAULT_BASE_URL}/budgets").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "budgets": [
                        {
                            "id": "b-1",
                            "name": "Main",
                            "currency_format": {"iso_code": "USD"},
                            "last_modified_on": "2026-05-15T00:00:00+00:00",
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "accounts": [
                        {
                            "id": "a-1",
                            "name": "Checking",
                            "type": "checking",
                            "balance": 0,
                            "on_budget": True,
                            "closed": False,
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/categories").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "category_groups": [
                        {
                            "id": "cg-1",
                            "name": "Spending",
                            "categories": [
                                {
                                    "id": "c-grocery",
                                    "category_group_id": "cg-1",
                                    "name": "Groceries",
                                    "hidden": False,
                                },
                                {
                                    "id": "c-gas",
                                    "category_group_id": "cg-1",
                                    "name": "Gas",
                                    "hidden": False,
                                },
                            ],
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/payees").mock(
        return_value=httpx.Response(
            200,
            json={"data": {"payees": [{"id": "p-store", "name": "Big Box Store"}]}},
        )
    )
    # Parent: category null, amount -50_000 (-$50). Subs: $20 to groceries, $30 to gas.
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "transactions": [
                        {
                            "id": "t-parent",
                            "account_id": "a-1",
                            "category_id": None,
                            "payee_id": "p-store",
                            "date": "2026-05-10",
                            "amount": -500000,
                            "memo": "trip",
                            "cleared": "cleared",
                            "approved": True,
                            "subtransactions": [
                                {
                                    "id": "t-sub-grocery",
                                    "transaction_id": "t-parent",
                                    "category_id": "c-grocery",
                                    "payee_id": None,
                                    "amount": -200000,
                                    "memo": "groceries",
                                },
                                {
                                    "id": "t-sub-gas",
                                    "transaction_id": "t-parent",
                                    "category_id": "c-gas",
                                    "payee_id": None,
                                    "amount": -300000,
                                    "memo": "gas",
                                },
                            ],
                        }
                    ]
                }
            },
        )
    )

    result = await run_sync(session, "test-token")
    assert result.transactions == 2

    parent = await session.get(Transaction, "t-parent")
    assert parent is None, "parent should NOT be persisted when subs are present"

    grocery = await session.get(Transaction, "t-sub-grocery")
    assert grocery is not None
    assert grocery.category_id == "c-grocery"
    assert grocery.amount_cents == -20000  # $200 in milliunits ÷ 10 = -20000 cents
    assert grocery.payee_id == "p-store"  # inherits parent payee
    assert grocery.account_id == "a-1"
    assert grocery.date.isoformat() == "2026-05-10"

    gas = await session.get(Transaction, "t-sub-gas")
    assert gas is not None
    assert gas.category_id == "c-gas"
    assert gas.amount_cents == -30000


@respx.mock
async def test_run_sync_replaces_pre_existing_parent_with_subs(
    session: AsyncSession,
) -> None:
    """If a parent transaction was persisted by an older sync (pre-fix), the
    next sync that sees subtransactions should delete the parent row so the
    same money isn't double-counted via parent + sub legs."""
    from datetime import UTC, date, datetime

    from app.models import Account, Budget

    # Seed budget + account first (parent's FKs).
    session.add(
        Budget(
            id="b-1",
            name="Main",
            currency="USD",
            last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    session.add(
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
    # Seed a pre-existing parent row to simulate the pre-fix sync's output.
    session.add(
        Transaction(
            id="t-parent",
            budget_id="b-1",
            account_id="a-1",
            category_id=None,
            payee_id=None,
            date=date(2026, 5, 10),
            amount_cents=-50000,
            memo="trip",
            cleared="cleared",
            approved=True,
        )
    )
    await session.commit()

    respx.get(f"{DEFAULT_BASE_URL}/budgets").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "budgets": [
                        {
                            "id": "b-1",
                            "name": "Main",
                            "currency_format": {"iso_code": "USD"},
                            "last_modified_on": "2026-05-15T00:00:00+00:00",
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/accounts").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "accounts": [
                        {
                            "id": "a-1",
                            "name": "Checking",
                            "type": "checking",
                            "balance": 0,
                            "on_budget": True,
                            "closed": False,
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/categories").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "category_groups": [
                        {
                            "id": "cg-1",
                            "name": "Spending",
                            "categories": [
                                {
                                    "id": "c-grocery",
                                    "category_group_id": "cg-1",
                                    "name": "Groceries",
                                    "hidden": False,
                                },
                            ],
                        }
                    ]
                }
            },
        )
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/payees").mock(
        return_value=httpx.Response(200, json={"data": {"payees": []}})
    )
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "transactions": [
                        {
                            "id": "t-parent",
                            "account_id": "a-1",
                            "category_id": None,
                            "payee_id": None,
                            "date": "2026-05-10",
                            "amount": -500000,
                            "memo": "trip",
                            "cleared": "cleared",
                            "approved": True,
                            "subtransactions": [
                                {
                                    "id": "t-sub-grocery",
                                    "transaction_id": "t-parent",
                                    "category_id": "c-grocery",
                                    "amount": -500000,
                                    "memo": "groceries",
                                },
                            ],
                        }
                    ]
                }
            },
        )
    )

    await run_sync(session, "test-token")

    parent = await session.get(Transaction, "t-parent")
    assert parent is None
    sub = await session.get(Transaction, "t-sub-grocery")
    assert sub is not None
    assert sub.amount_cents == -50000
