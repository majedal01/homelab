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
