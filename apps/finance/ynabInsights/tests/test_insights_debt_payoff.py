"""Debt Payoff (v2.6g).

The interesting cases:

1. Active paydown -> card fires with projected date.
2. Growing balance (more charges than payments) -> skipped.
3. No credit accounts -> no cards (correct empty state).
4. Closed credit account with residual balance -> skipped.
5. Projection > 10 years (too slow) -> skipped to avoid a discouraging
   "paid off in 2042" headline.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.insights.debt_payoff import DebtPayoffGenerator
from app.snapshot.models import Account, Transaction, YnabSnapshot

CHECKING = Account(
    id="acct-chk",
    name="Checking",
    type="checking",
    on_budget=True,
    closed=False,
    balance_cents=500000,
)


def _credit(balance_cents: int, **kw: Any) -> Account:
    return Account(
        id=kw.get("id", "acct-cc"),
        name=kw.get("name", "Credit Card"),
        type=kw.get("type", "creditCard"),
        on_budget=True,
        closed=kw.get("closed", False),
        balance_cents=balance_cents,
    )


def _snapshot(accounts: list[Account], txns: list[Transaction]) -> YnabSnapshot:
    return YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=accounts,
        categories=[],
        payees=[],
        transactions=txns,
    )


def _cc_txn(d: date, amount: int, account_id: str = "acct-cc") -> Transaction:
    return Transaction(
        id=f"t-{account_id}-{d.isoformat()}-{amount}",
        date=d,
        amount_cents=amount,
        account_id=account_id,
    )


async def test_active_paydown_fires_card() -> None:
    """\$3k debt + \$300/mo net paydown over 3 months -> ~10 month payoff."""
    today = date.today()
    cc = _credit(-3_000_00)
    txns: list[Transaction] = []
    # Each of the last 3 months: $500 in payments minus $200 in charges = +$300 net
    for months_back in (3, 2, 1):
        anchor = today - timedelta(days=30 * months_back)
        txns.append(_cc_txn(anchor, +500_00))
        txns.append(_cc_txn(anchor + timedelta(days=5), -200_00))
    snapshot = _snapshot([CHECKING, cc], txns)
    insights = await DebtPayoffGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    payload = insights[0].structured_data
    assert payload["current_debt_cents"] == 3_000_00
    assert payload["avg_monthly_paydown_cents"] > 0
    assert 5 <= payload["projected_months_to_payoff"] <= 15


async def test_growing_balance_skipped() -> None:
    """Charges outpace payments -> non-positive paydown -> no card."""
    today = date.today()
    cc = _credit(-3_000_00)
    txns: list[Transaction] = []
    # 3 months of $200 payments + $400 charges per month = -$200 net
    for months_back in (3, 2, 1):
        anchor = today - timedelta(days=30 * months_back)
        txns.append(_cc_txn(anchor, +200_00))
        txns.append(_cc_txn(anchor + timedelta(days=5), -400_00))
    snapshot = _snapshot([CHECKING, cc], txns)
    insights = await DebtPayoffGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_no_credit_accounts_no_card() -> None:
    snapshot = _snapshot([CHECKING], [])
    insights = await DebtPayoffGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_closed_account_skipped() -> None:
    today = date.today()
    cc = _credit(-1_000_00, closed=True)
    txns = [_cc_txn(today - timedelta(days=15), +200_00)]
    snapshot = _snapshot([CHECKING, cc], txns)
    insights = await DebtPayoffGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_minimum_payments_over_10_years_skipped() -> None:
    """\$30k debt, \$20/mo paydown -> 1500 months -> skipped (>120)."""
    today = date.today()
    cc = _credit(-30_000_00)
    txns: list[Transaction] = []
    for months_back in (3, 2, 1):
        anchor = today - timedelta(days=30 * months_back)
        txns.append(_cc_txn(anchor, +20_00))
    # 3mo signal is $20/mo, exactly the fallback floor — generator widens
    # to 6mo lookback but no further data is there, so paydown stays low
    # and projection will be > 10 years.
    snapshot = _snapshot([CHECKING, cc], txns)
    insights = await DebtPayoffGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_line_of_credit_treated_as_debt() -> None:
    """LoC accounts qualify for the payoff card alongside credit cards."""
    today = date.today()
    loc = _credit(-5_000_00, id="acct-loc", name="HELOC", type="lineOfCredit")
    txns: list[Transaction] = []
    for months_back in (3, 2, 1):
        anchor = today - timedelta(days=30 * months_back)
        txns.append(_cc_txn(anchor, +400_00, account_id="acct-loc"))
    snapshot = _snapshot([CHECKING, loc], txns)
    insights = await DebtPayoffGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["account_type"] == "lineOfCredit"
