"""Goals generator (v2.6h): inferred-progress cards.

Native per-category trajectory cards were dropped (users barely set YNAB
goals). The generator now emits emergency_fund_coverage and
savings_rate_trend, falling back to goal_setup_prompt when neither can be
computed. Each emitted card carries its own card_type via
GeneratedInsight.card_type.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from app.insights.goal_trajectory import GoalTrajectoryGenerator
from app.snapshot.models import Account, Category, Transaction, YnabSnapshot

CHECKING = Account(
    id="acct-1",
    name="Checking",
    type="checking",
    on_budget=True,
    closed=False,
    balance_cents=600000,  # $6,000 liquid cash
)
GROC = Category(id="cat-groc", name="Groceries")


def _month_first(today: date, months_back: int) -> date:
    y, m = today.year, today.month
    for _ in range(months_back):
        if m == 1:
            y, m = y - 1, 12
        else:
            m -= 1
    return date(y, m, 1)


def _snapshot(txns: list[Transaction], *, accounts: list[Account] | None = None) -> YnabSnapshot:
    return YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=accounts if accounts is not None else [CHECKING],
        categories=[GROC],
        payees=[],
        transactions=txns,
    )


def _txn(d: date, amount: int, *, category_id: str | None = "cat-groc", **kw: Any) -> Transaction:
    return Transaction(
        id=f"t-{d.isoformat()}-{amount}",
        date=d,
        amount_cents=amount,
        account_id="acct-1",
        category_id=category_id,
        **kw,
    )


async def test_emergency_fund_and_savings_rate_emitted() -> None:
    """Six complete months of $3,000 spend and $5,000 income, $6,000 cash:
    coverage ~2 months and a 40% savings rate."""
    today = date.today()
    txns: list[Transaction] = []
    for i in range(1, 7):  # six complete prior months
        first = _month_first(today, i)
        txns.append(_txn(first, 500000, category_id=None))  # income -> RTA/null
        txns.append(_txn(first, -300000))  # spending
    insights = await GoalTrajectoryGenerator().run(_snapshot(txns), anthropic_key=None)
    by_type = {i.card_type: i for i in insights}
    assert set(by_type) == {"emergency_fund_coverage", "savings_rate_trend"}

    ef = by_type["emergency_fund_coverage"].structured_data
    assert ef["card_type"] == "emergency_fund_coverage"
    assert ef["coverage_months"] == 2.0
    assert ef["avg_monthly_spending_cents"] == 300000

    sr = by_type["savings_rate_trend"].structured_data
    assert sr["card_type"] == "savings_rate_trend"
    assert sr["average_savings_rate"] == 0.4
    assert sr["latest_savings_rate"] == 0.4


async def test_savings_rate_direction_up() -> None:
    """Savings rate climbs across the window -> direction 'up'."""
    today = date.today()
    txns: list[Transaction] = []
    # Older months: lower savings rate; recent months: higher.
    plan = {6: -400000, 5: -400000, 4: -350000, 3: -200000, 2: -150000, 1: -100000}
    for months_back, spend in plan.items():
        first = _month_first(today, months_back)
        txns.append(_txn(first, 500000, category_id=None))
        txns.append(_txn(first, spend))
    insights = await GoalTrajectoryGenerator().run(_snapshot(txns), anthropic_key=None)
    sr = next(i.structured_data for i in insights if i.card_type == "savings_rate_trend")
    assert sr["direction"] == "up"


async def test_falls_back_to_goal_setup_prompt() -> None:
    """No income and no completed-month spending history -> neither inferred
    card computes -> goal_setup_prompt fallback, stamped goal_setup_prompt."""
    today = date.today()
    # Spending only in the current (partial) month, which is dropped from the
    # complete-month baseline; no income at all.
    txns = [_txn(date(today.year, today.month, 1), -100000)]
    insights = await GoalTrajectoryGenerator().run(_snapshot(txns), anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].card_type == "goal_setup_prompt"
    assert insights[0].structured_data["card_type"] == "goal_setup_prompt"


async def test_no_data_emits_nothing() -> None:
    """Empty snapshot: no inferred cards, and no spending candidates for the
    prompt -> emit nothing rather than a useless card."""
    insights = await GoalTrajectoryGenerator().run(_snapshot([]), anthropic_key=None)
    assert insights == []


async def test_negative_cash_skips_emergency_fund() -> None:
    """If liquid cash is negative we can't express meaningful coverage; the
    emergency-fund card is skipped (savings rate may still fire)."""
    today = date.today()
    overdrawn = Account(
        id="acct-1",
        name="Checking",
        type="checking",
        on_budget=True,
        closed=False,
        balance_cents=-5000,
    )
    txns: list[Transaction] = []
    for i in range(1, 7):
        first = _month_first(today, i)
        txns.append(_txn(first, 500000, category_id=None))
        txns.append(_txn(first, -300000))
    insights = await GoalTrajectoryGenerator().run(
        _snapshot(txns, accounts=[overdrawn]), anthropic_key=None
    )
    types = {i.card_type for i in insights}
    assert "emergency_fund_coverage" not in types
    assert "savings_rate_trend" in types
