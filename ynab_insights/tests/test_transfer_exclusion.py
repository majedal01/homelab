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

    # Rent is real net spending - included
    assert by_name["Rent"] == -150000
    # Transfer outflow (-50000) must not leak into Rent
    assert by_name["Rent"] != -200000
    # Uncategorized bucket: paycheck (+500000) and atm fee (-2500) sum to a
    # positive net, so the bucket is correctly omitted from the spending view
    # by the "net outflow only" HAVING filter.
    assert "Uncategorized" not in by_name


async def test_monthly_summary_excludes_transfers_from_inflow_and_outflow(
    seeded: AsyncSession,
) -> None:
    today = date.today()
    result = await monthly_summary(seeded, "b-1", today.year, today.month)

    # Inflow ("Total Income"): YNAB defines this as positive amounts in the
    # null category (Ready to Assign). Only the paycheck qualifies; the
    # transfer inflow is excluded by the transfer filter.
    assert result.total_inflow_cents == 500000
    # Outflow ("Total Expenses"): sum of all amounts on categorized rows on
    # on-budget accounts. Rent is the only categorized row in seed — atm fee
    # is uncategorized so it doesn't count toward expenses, and the transfer
    # outflow is excluded.
    assert result.total_outflow_cents == -150000
    # Transaction count includes every on-budget non-transfer row regardless
    # of category — paycheck, rent, atm fee.
    assert result.transaction_count == 3


async def test_monthly_summary_recognizes_ynab_income_category(
    db_session: AsyncSession,
) -> None:
    """YNAB tags real-world paychecks to the built-in 'Inflow: Ready to
    Assign' category, not to a null category. The aggregate logic has to
    recognize that name and treat positive amounts there as income (NOT
    fold them into expenses)."""
    today = date.today()
    db_session.add_all(
        [
            Budget(
                id="b-i",
                name="I",
                currency="USD",
                last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
            ),
            Account(
                id="a-i",
                budget_id="b-i",
                name="Checking",
                type="checking",
                balance_cents=0,
                on_budget=True,
                closed=False,
            ),
            # YNAB ships this category in every budget; income posts here.
            Category(
                id="c-rta",
                budget_id="b-i",
                category_group_id=None,
                name="Inflow: Ready to Assign",
                hidden=False,
            ),
            Category(
                id="c-rent",
                budget_id="b-i",
                category_group_id=None,
                name="Rent",
                hidden=False,
            ),
            # Income tagged to RTA — the realistic shape.
            Transaction(
                id="t-paycheck",
                budget_id="b-i",
                account_id="a-i",
                category_id="c-rta",
                payee_id=None,
                date=today,
                amount_cents=977003,
                memo="paycheck",
                cleared="cleared",
                approved=True,
            ),
            # Real spending in an expense category.
            Transaction(
                id="t-rent",
                budget_id="b-i",
                account_id="a-i",
                category_id="c-rent",
                payee_id=None,
                date=today,
                amount_cents=-381300,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()

    result = await monthly_summary(db_session, "b-i", today.year, today.month)
    # Inflow MUST count the RTA-tagged paycheck.
    assert result.total_inflow_cents == 977003
    # Outflow MUST NOT count the RTA-tagged paycheck — only rent.
    assert result.total_outflow_cents == -381300

    # The donut/categories view must not list RTA as an expense category.
    cats = await spending_by_category(db_session, "b-i", today.replace(day=1), today)
    names = {c.category_name for c in cats}
    assert "Inflow: Ready to Assign" not in names
    assert "Rent" in names


async def test_transfer_to_off_budget_account_counts_as_spending(
    db_session: AsyncSession,
) -> None:
    """YNAB's reports treat a transfer to an OFF-budget tracking account
    (loan, investment, asset) as real spending — paying down a car loan
    is a Car Payment expense even though it's modeled as a transfer.

    Pinned this test because the previous filter excluded ALL
    transfer-payee rows regardless of the destination account's
    on_budget flag, which silently dropped $687.52 of real spending on
    the live "Majood & Choona" budget."""
    today = date.today()
    db_session.add_all(
        [
            Budget(
                id="b-x",
                name="X",
                currency="USD",
                last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
            ),
            # On-budget source
            Account(
                id="a-checking",
                budget_id="b-x",
                name="Checking",
                type="checking",
                balance_cents=0,
                on_budget=True,
                closed=False,
            ),
            # Off-budget tracking destination (loan, investment, etc.)
            Account(
                id="a-loan",
                budget_id="b-x",
                name="Auto Loan",
                type="autoLoan",
                balance_cents=0,
                on_budget=False,
                closed=False,
            ),
            # On-budget destination (control: should still be excluded)
            Account(
                id="a-savings",
                budget_id="b-x",
                name="Savings",
                type="savings",
                balance_cents=0,
                on_budget=True,
                closed=False,
            ),
            Category(
                id="c-car",
                budget_id="b-x",
                category_group_id=None,
                name="Car Payment",
                hidden=False,
            ),
            # Transfer-to-off-budget payee
            Payee(
                id="p-xfer-loan",
                budget_id="b-x",
                name="Transfer : Auto Loan",
                transfer_account_id="a-loan",
            ),
            # Transfer-to-on-budget payee (control)
            Payee(
                id="p-xfer-savings",
                budget_id="b-x",
                name="Transfer : Savings",
                transfer_account_id="a-savings",
            ),
            # The real expense: Car Payment routed via transfer payee
            Transaction(
                id="t-car-payment",
                budget_id="b-x",
                account_id="a-checking",
                category_id="c-car",
                payee_id="p-xfer-loan",
                date=today,
                amount_cents=-68752,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            # The auto-paired entry on the loan account itself
            Transaction(
                id="t-loan-side",
                budget_id="b-x",
                account_id="a-loan",
                category_id=None,
                payee_id="p-xfer-loan",
                date=today,
                amount_cents=68752,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            # Control: a true internal transfer to on-budget Savings
            # (should STILL be excluded from spending).
            Transaction(
                id="t-true-xfer",
                budget_id="b-x",
                account_id="a-checking",
                category_id=None,
                payee_id="p-xfer-savings",
                date=today,
                amount_cents=-50000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()

    result = await spending_by_category(db_session, "b-x", today.replace(day=1), today)
    by_name = {r.category_name: r.spent_cents for r in result}
    # Car Payment MUST appear — transfer to off-budget account is real spending.
    assert by_name.get("Car Payment") == -68752
    # The Savings transfer MUST NOT leak into any category.
    assert -50000 not in by_name.values()

    summary = await monthly_summary(db_session, "b-x", today.year, today.month)
    # Total outflow includes the Car Payment, NOT the Savings transfer.
    assert summary.total_outflow_cents == -68752


async def test_spending_by_category_nets_inflows_against_outflows(
    db_session: AsyncSession,
) -> None:
    """Reimbursable Expenses: a $100 outflow tagged to the category plus a
    $100 inflow tagged to the same category should net to zero and be
    omitted from the spending view entirely. Categories that net positive
    (more refunds than spend) are also omitted."""
    today = date.today()
    db_session.add_all(
        [
            Budget(
                id="b-r",
                name="R",
                currency="USD",
                last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
            ),
            Account(
                id="a-r",
                budget_id="b-r",
                name="Checking",
                type="checking",
                balance_cents=0,
                on_budget=True,
                closed=False,
            ),
            Category(
                id="c-reimb",
                budget_id="b-r",
                category_group_id=None,
                name="Reimbursable Expenses",
                hidden=False,
            ),
            Category(
                id="c-net-refund",
                budget_id="b-r",
                category_group_id=None,
                name="Net Refunded",
                hidden=False,
            ),
            Category(
                id="c-real",
                budget_id="b-r",
                category_group_id=None,
                name="Groceries",
                hidden=False,
            ),
            # Reimbursable Expenses: cancels out.
            Transaction(
                id="t-reimb-out",
                budget_id="b-r",
                account_id="a-r",
                category_id="c-reimb",
                payee_id=None,
                date=today,
                amount_cents=-10000,
                memo="lunch",
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-reimb-in",
                budget_id="b-r",
                account_id="a-r",
                category_id="c-reimb",
                payee_id=None,
                date=today,
                amount_cents=10000,
                memo="employer refund",
                cleared="cleared",
                approved=True,
            ),
            # Net Refunded: inflow > outflow, so this category is net-positive.
            Transaction(
                id="t-refund-out",
                budget_id="b-r",
                account_id="a-r",
                category_id="c-net-refund",
                payee_id=None,
                date=today,
                amount_cents=-2000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            Transaction(
                id="t-refund-in",
                budget_id="b-r",
                account_id="a-r",
                category_id="c-net-refund",
                payee_id=None,
                date=today,
                amount_cents=5000,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
            # Real net spending.
            Transaction(
                id="t-groc",
                budget_id="b-r",
                account_id="a-r",
                category_id="c-real",
                payee_id=None,
                date=today,
                amount_cents=-7500,
                memo=None,
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()

    result = await spending_by_category(db_session, "b-r", today.replace(day=1), today)
    names = {r.category_name for r in result}
    assert "Groceries" in names
    assert "Reimbursable Expenses" not in names  # net to zero
    assert "Net Refunded" not in names  # net positive (more refund than spend)
