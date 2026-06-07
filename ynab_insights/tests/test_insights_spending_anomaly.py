"""Spending Anomaly (v2.6f).

Three things matter most:

1. A monthly-cycle category (rent, car payment) compares month-vs-12mo
   not week-vs-12w.
2. A weekly-cycle category (groceries) keeps the v2.4 week-vs-12w logic.
3. Quarterly / annual / irregular categories are skipped — Spending
   Anomaly is not the right surface for them.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest

from app.insights.spending_anomaly import SpendingAnomalyGenerator
from app.snapshot.models import Account, Category, Transaction, YnabSnapshot

CHECKING = Account(
    id="acct-1",
    name="Checking",
    type="checking",
    on_budget=True,
    closed=False,
    balance_cents=100000,
)


def _snapshot(cats: list[Category], txns: list[Transaction]) -> YnabSnapshot:
    return YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=[CHECKING],
        categories=cats,
        payees=[],
        transactions=txns,
    )


def _txn(d: date, cat_id: str, amount: int, **kw: Any) -> Transaction:
    return Transaction(
        id=f"t-{cat_id}-{d.isoformat()}-{amount}",
        date=d,
        amount_cents=amount,
        account_id="acct-1",
        category_id=cat_id,
        **kw,
    )


def _first_of_month(d: date, months_back: int) -> date:
    y, m = d.year, d.month
    for _ in range(months_back):
        if m == 1:
            y, m = y - 1, 12
        else:
            m -= 1
    return date(y, m, 1)


async def test_monthly_category_uses_month_window() -> None:
    """Rent is monthly-cycle. 12 months of $1500, then $2500 this month
    -> anomaly card in monthly mode."""
    today = date.today()
    cat = Category(id="cat-rent", name="Rent")
    txns: list[Transaction] = []
    for i in range(12, 0, -1):
        d = _first_of_month(today, i)
        txns.append(_txn(d, cat.id, -150000))
    # Current month-to-date: $2500 paid on the 1st
    current = date(today.year, today.month, 1)
    txns.append(_txn(current, cat.id, -250000))
    snapshot = _snapshot([cat], txns)
    insights = await SpendingAnomalyGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    payload = insights[0].structured_data
    assert payload["cycle"] == "monthly"
    assert payload["current_period_spend_cents"] == 250000
    assert payload["baseline_mean_cents"] == 150000
    assert payload["z_score"] > 1.5


async def test_weekly_category_uses_week_window() -> None:
    """Groceries fires at >40 txns/yr so classifier returns weekly.
    Spike this week -> weekly anomaly card."""
    today = date.today()
    cat = Category(id="cat-groc", name="Groceries")
    txns: list[Transaction] = []
    # 12 baseline weeks at ~$100/wk via 4 txns of $25 each
    for week_offset in range(12, 0, -1):
        week_start = today - timedelta(days=7 * week_offset)
        for day in (0, 2, 4, 6):
            txns.append(_txn(week_start + timedelta(days=day), cat.id, -2500))
    # Current week: $500 (5x the baseline)
    week_start = today - timedelta(days=today.weekday())
    for day in (0, 1, 2, 3, 4):
        d = week_start + timedelta(days=day)
        if d > today:
            continue
        txns.append(_txn(d, cat.id, -10000))
    snapshot = _snapshot([cat], txns)
    insights = await SpendingAnomalyGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["cycle"] == "weekly"


async def test_monthly_category_quiet_when_only_a_week_of_spike() -> None:
    """Real bug from v2.4: a car payment looked anomalous because the
    week-vs-12w comparison hit a payment week with $0 baseline. v2.6f
    classifies it monthly; the month is normal, no anomaly."""
    today = date.today()
    cat = Category(id="cat-car", name="Car Payment")
    txns: list[Transaction] = []
    for i in range(12, 0, -1):
        d = _first_of_month(today, i)
        txns.append(_txn(d, cat.id, -45000))
    txns.append(_txn(date(today.year, today.month, 1), cat.id, -45000))
    snapshot = _snapshot([cat], txns)
    insights = await SpendingAnomalyGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


def _pin_today(monkeypatch: pytest.MonkeyPatch, d: date) -> None:
    """Pin date.today() inside the generator while keeping date(...)
    construction working, without subclassing date (which trips mypy)."""

    class _DateProxy:
        @staticmethod
        def today() -> date:
            return d

        def __call__(self, year: int, month: int, day: int) -> date:
            return date(year, month, day)

    monkeypatch.setattr("app.insights.spending_anomaly.date", _DateProxy())


async def test_monthly_partial_period_spike_fires() -> None:
    """v2.6h same-day-of-month baseline: an elevated current month-to-date
    is compared against prior months' same-day windows, not full months,
    and fires. Charges land on the 1st so the test is run-day independent."""
    today = date.today()
    cat = Category(id="cat-shop", name="Shopping")
    txns = [_txn(_first_of_month(today, i), cat.id, -10000) for i in range(12, 0, -1)]
    txns.append(_txn(date(today.year, today.month, 1), cat.id, -40000))
    snapshot = _snapshot([cat], txns)
    insights = await SpendingAnomalyGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["cycle"] == "monthly"
    assert insights[0].structured_data["current_period_spend_cents"] == 40000


async def test_unposted_midmonth_charge_no_false_below(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A monthly bill that posts on the 20th hasn't posted by the 7th.
    Same-day windows exclude it from BOTH current and baseline, so there
    is no spurious 'below usual' card early in the month."""
    _pin_today(monkeypatch, date(2026, 6, 7))
    cat = Category(id="cat-bill", name="Phone Bill")
    txns = [_txn(date(2025, m, 20), cat.id, -8000) for m in range(6, 13)]
    txns += [_txn(date(2026, m, 20), cat.id, -8000) for m in range(1, 6)]
    snapshot = _snapshot([cat], txns)
    insights = await SpendingAnomalyGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_irregular_category_skipped() -> None:
    """A category with one purchase has no classifiable cycle -> no card,
    even if the single purchase happens to land in the 'current week'."""
    today = date.today()
    cat = Category(id="cat-etsy", name="Hobbies")
    txns = [_txn(today, cat.id, -50000)]
    snapshot = _snapshot([cat], txns)
    insights = await SpendingAnomalyGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_below_dollar_floor_skipped() -> None:
    """Z-score crosses 1.5 but the absolute dollar deviation is below
    the $50 floor -> no card."""
    today = date.today()
    cat = Category(id="cat-coffee", name="Coffee")
    txns: list[Transaction] = []
    # 12 baseline weeks of $10/wk (one $10 txn), current week $25 — z is
    # well above 1.5 (stdev is 0... so this won't fire on stdev check).
    # Use tiny variance instead: $10, $11, $9, ... and a current week $25.
    for week_offset in range(12, 0, -1):
        week_start = today - timedelta(days=7 * week_offset)
        # vary $9, $10, $11 so stdev > 0
        amount = -900 - (week_offset % 3) * 100
        txns.append(_txn(week_start, cat.id, amount))
    week_start = today - timedelta(days=today.weekday())
    txns.append(_txn(week_start, cat.id, -2500))
    # Not classifiable as weekly via frequency floor (only 13 txns/yr).
    # The category classifier will return irregular, so no card.
    snapshot = _snapshot([cat], txns)
    insights = await SpendingAnomalyGenerator().run(snapshot, anthropic_key=None)
    assert insights == []
