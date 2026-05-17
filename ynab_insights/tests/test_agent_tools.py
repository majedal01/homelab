"""Tests for the agent's tool functions. Each is exercised directly against
seeded SQLite, independent of the Anthropic SDK."""

from datetime import UTC, date, datetime, timedelta

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import (
    TOOL_REGISTRY,
    ListAccountsInput,
    ListBudgetsInput,
    ListCategoriesInput,
    MonthlySummaryInput,
    SpendingByCategoryInput,
    TransactionsInput,
    _list_accounts,
    _list_budgets,
    _list_categories,
    _monthly_summary,
    _spending_by_category,
    _transactions,
)
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
                name="Old",
                type="savings",
                balance_cents=0,
                on_budget=True,
                closed=True,
            ),
            Category(
                id="c-rent", budget_id="b-1", category_group_id=None, name="Rent", hidden=False
            ),
            Category(
                id="c-groc", budget_id="b-1", category_group_id=None, name="Groceries", hidden=False
            ),
            Payee(id="p-1", budget_id="b-1", name="Landlord", transfer_account_id=None),
            Payee(id="p-2", budget_id="b-1", name="Whole Foods Market", transfer_account_id=None),
            Transaction(
                id="t-rent",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-rent",
                payee_id="p-1",
                date=today,
                amount_cents=-150000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-groc",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-groc",
                payee_id="p-2",
                date=today,
                amount_cents=-12000,
                memo="weekly",
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-paycheck",
                budget_id="b-1",
                account_id="a-1",
                category_id=None,
                payee_id=None,
                date=today,
                amount_cents=500000,
                memo="paycheck",
                cleared="cleared",
                approved=True,
            ),
            # Old, outside the current month
            Transaction(
                id="t-old",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-rent",
                payee_id="p-1",
                date=today - timedelta(days=200),
                amount_cents=-100000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()
    return db_session


async def test_list_budgets_returns_seeded(seeded: AsyncSession) -> None:
    result = await _list_budgets(seeded, ListBudgetsInput())
    assert len(result) == 1
    assert result[0]["name"] == "Main"
    assert result[0]["currency"] == "USD"


async def test_list_accounts_excludes_closed(seeded: AsyncSession) -> None:
    result = await _list_accounts(seeded, ListAccountsInput(budget_id="b-1"))
    names = [a["name"] for a in result]
    assert names == ["Checking"]
    assert result[0]["balance_dollars"] == 1250.00


async def test_list_categories(seeded: AsyncSession) -> None:
    result = await _list_categories(seeded, ListCategoriesInput(budget_id="b-1"))
    assert {c["name"] for c in result} == {"Rent", "Groceries"}


async def test_spending_by_category_for_current_month(seeded: AsyncSession) -> None:
    today = date.today()
    start = today.replace(day=1)
    result = await _spending_by_category(
        seeded, SpendingByCategoryInput(budget_id="b-1", start_date=start, end_date=today)
    )
    # Rent is highest spend
    assert result[0]["category_name"] == "Rent"
    assert result[0]["spent_dollars"] == 1500.00
    # Groceries next
    by_name = {r["category_name"]: r["spent_dollars"] for r in result}
    assert by_name["Groceries"] == 120.00


async def test_transactions_payee_name_contains_is_case_insensitive(
    seeded: AsyncSession,
) -> None:
    result = await _transactions(
        seeded, TransactionsInput(budget_id="b-1", payee_name_contains="whole foods")
    )
    assert len(result) == 1
    assert result[0]["payee_name"] == "Whole Foods Market"
    assert result[0]["amount_dollars"] == -120.00


async def test_transactions_category_filter(seeded: AsyncSession) -> None:
    result = await _transactions(seeded, TransactionsInput(budget_id="b-1", category_id="c-rent"))
    ids = {t["id"] for t in result}
    assert ids == {"t-rent", "t-old"}


async def test_monthly_summary_separates_inflow_outflow(seeded: AsyncSession) -> None:
    today = date.today()
    result = await _monthly_summary(
        seeded, MonthlySummaryInput(budget_id="b-1", year=today.year, month=today.month)
    )
    assert result["total_inflow_dollars"] == 5000.00
    assert result["total_outflow_dollars"] == -1620.00
    assert result["transaction_count"] == 3
    # Top categories: Rent first
    assert result["top_categories"][0]["category_name"] == "Rent"


async def test_registry_anthropic_specs_are_well_formed() -> None:
    for tool in TOOL_REGISTRY.values():
        spec = tool.to_anthropic_spec()
        assert spec["name"] == tool.name
        assert spec["description"]
        assert spec["input_schema"]["type"] == "object"
