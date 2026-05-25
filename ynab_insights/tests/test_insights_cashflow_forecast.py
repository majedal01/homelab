"""Cashflow Forecast (v2.6f).

The headline change: starting_balance_cents reflects only cash-equivalent
accounts (checking/savings/cash). Credit-card balances surface as a
separate credit_card_debt_cents secondary metric so the projection
doesn't show a user with revolved credit as "owing" their cash position.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.insights.cashflow_forecast import CashflowForecastGenerator
from app.snapshot.models import Account, Category, Transaction, YnabSnapshot

INCOME = Category(id="cat-ready", name="Inflow: Ready to Assign")


def _txn(d: date, amount: int, account_id: str = "acct-checking", **kw: Any) -> Transaction:
    return Transaction(
        id=f"t-{account_id}-{d.isoformat()}-{amount}",
        date=d,
        amount_cents=amount,
        account_id=account_id,
        **kw,
    )


def _snapshot(accounts: list[Account], txns: list[Transaction]) -> YnabSnapshot:
    return YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=accounts,
        categories=[INCOME],
        payees=[],
        transactions=txns,
    )


async def test_cash_only_starting_balance_excludes_credit_debt() -> None:
    """User with $3k checking + $5k credit-card debt sees $3k cash today,
    not -$2k. Credit debt is surfaced separately."""
    accounts = [
        Account(
            id="acct-checking",
            name="Checking",
            type="checking",
            on_budget=True,
            closed=False,
            balance_cents=3_000_00,
        ),
        Account(
            id="acct-cc",
            name="Credit",
            type="creditCard",
            on_budget=True,
            closed=False,
            balance_cents=-5_000_00,
        ),
    ]
    today = date.today()
    txns: list[Transaction] = []
    # Add a few in-window transactions so the generator doesn't bail.
    txns.append(_txn(today - timedelta(days=10), 3_000_00, category_id="cat-ready"))
    txns.append(_txn(today - timedelta(days=20), -1_500_00, category_id="cat-spend"))
    snapshot = _snapshot(accounts, txns)
    insights = await CashflowForecastGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    payload = insights[0].structured_data
    assert payload["starting_balance_cents"] == 3_000_00
    assert payload["credit_card_debt_cents"] == 5_000_00


async def test_savings_counted_in_cash_balance() -> None:
    """Cash accounts: checking + savings + cash. All three sum into
    starting_balance_cents."""
    accounts = [
        Account(
            id="acct-checking",
            name="Checking",
            type="checking",
            on_budget=True,
            closed=False,
            balance_cents=1_000_00,
        ),
        Account(
            id="acct-savings",
            name="Savings",
            type="savings",
            on_budget=True,
            closed=False,
            balance_cents=4_000_00,
        ),
        Account(
            id="acct-cash",
            name="Wallet",
            type="cash",
            on_budget=True,
            closed=False,
            balance_cents=100_00,
        ),
    ]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=10), 2_000_00, category_id="cat-ready"),
        _txn(today - timedelta(days=20), -500_00, category_id="cat-spend"),
    ]
    snapshot = _snapshot(accounts, txns)
    insights = await CashflowForecastGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["starting_balance_cents"] == 5_100_00
    assert insights[0].structured_data["credit_card_debt_cents"] == 0


async def test_closed_credit_card_excluded() -> None:
    """A closed credit card with a residual negative balance no longer
    counts as debt — YNAB wouldn't include it in net worth either."""
    accounts = [
        Account(
            id="acct-checking",
            name="Checking",
            type="checking",
            on_budget=True,
            closed=False,
            balance_cents=2_000_00,
        ),
        Account(
            id="acct-cc-closed",
            name="Old credit",
            type="creditCard",
            on_budget=True,
            closed=True,
            balance_cents=-1_000_00,
        ),
    ]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=5), 1_000_00, category_id="cat-ready"),
    ]
    snapshot = _snapshot(accounts, txns)
    insights = await CashflowForecastGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["credit_card_debt_cents"] == 0
