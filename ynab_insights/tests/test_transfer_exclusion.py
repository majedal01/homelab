"""Verify transfer payees are excluded from spending and summary aggregates."""

from datetime import UTC, date, datetime

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Budget, Category, Payee, Transaction
from app.services.queries import monthly_summary, spending_by_category


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
                id="a-checking",
                budget_id="b-1",
                name="Checking",
                type="checking",
                balance_cents=10000,
                on_budget=True,
                closed=False,
            ),
            Account(
                id="a-savings",
                budget_id="b-1",
                name="Savings",
                type="savings",
                balance_cents=10000,
                on_budget=True,
                closed=False,
            ),
            Category(
                id="c-rent", budget_id="b-1", category_group_id=None, name="Rent", hidden=False
            ),
            # Regular payee (real spending)
            Payee(id="p-landlord", budget_id="b-1", name="Landlord", transfer_account_id=None),
            # Transfer payee: represents the "other side" pointing at savings
            Payee(
                id="p-transfer-to-savings",
                budget_id="b-1",
                name="Transfer : Savings",
                transfer_account_id="a-savings",
            ),
            # Real spending - rent
            Transaction(
                id="t-rent",
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
            # Account-to-account transfer outflow (FROM checking) - should be EXCLUDED
            Transaction(
                id="t-xfer-out",
                budget_id="b-1",
                account_id="a-checking",
                category_id=None,
                payee_id="p-transfer-to-savings",
                date=today,
                amount_cents=-50000,
                memo="moving to savings",
                cleared="cleared",
                approved=True,
            ),
            # Account-to-account transfer inflow (INTO savings) - should also be EXCLUDED
            Transaction(
                id="t-xfer-in",
                budget_id="b-1",
                account_id="a-savings",
                category_id=None,
                payee_id="p-transfer-to-savings",
                date=today,
                amount_cents=50000,
                memo="from checking",
                cleared="cleared",
                approved=True,
            ),
            # Real income (paycheck), no payee
            Transaction(
                id="t-paycheck",
                budget_id="b-1",
                account_id="a-checking",
                category_id=None,
                payee_id=None,
                date=today,
                amount_cents=500000,
                memo="paycheck",
                cleared="cleared",
                approved=True,
            ),
            # Genuinely uncategorized spending (no payee, no category) - should be KEPT
            Transaction(
                id="t-uncat-spend",
                budget_id="b-1",
                account_id="a-checking",
                category_id=None,
                payee_id=None,
                date=today,
                amount_cents=-2500,
                memo="atm fee?",
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()
    return db_session


async def test_spending_by_category_excludes_transfer_outflow(seeded: AsyncSession) -> None:
    today = date.today()
    result = await spending_by_category(seeded, "b-1", today.replace(day=1), today)
    by_name = {r.category_name or "Uncategorized": r.spent_cents for r in result}

    # Rent is real spending - included
    assert by_name["Rent"] == -150000
    # ATM fee (no payee) - included as Uncategorized
    assert by_name["Uncategorized"] == -2500
    # Transfer outflow (-50000) MUST NOT appear in either bucket
    assert by_name["Rent"] != -200000  # would be -150000 + -50000 if transfer leaked


async def test_monthly_summary_excludes_transfers_from_inflow_and_outflow(
    seeded: AsyncSession,
) -> None:
    today = date.today()
    result = await monthly_summary(seeded, "b-1", today.year, today.month)

    # Inflow: only the paycheck (+500000). Transfer inflow (+50000) excluded.
    assert result.total_inflow_cents == 500000
    # Outflow: rent (-150000) + atm fee (-2500). Transfer outflow (-50000) excluded.
    assert result.total_outflow_cents == -152500
    # Count: 5 total in seed - 2 transfers = 3 (paycheck, rent, atm)
    assert result.transaction_count == 3
