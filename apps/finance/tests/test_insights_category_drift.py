"""Category Drift (v2.6f).

The interesting cases on a real budget:

1. A steadily-rising monthly category fires a quarter-over-quarter card.
2. An annual category with a seasonal spike (tax prep in Q1) does NOT
   fire just because the surrounding 9 months were quiet — it goes
   year-over-year instead.
3. A category with only 4 months of history is skipped (not enough
   baseline; Spending Anomaly handles it).
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Any

from app.insights.category_drift import CategoryDriftGenerator
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


def _month_anchor(today: date, months_back: int) -> date:
    y, m = today.year, today.month
    for _ in range(months_back):
        if m == 1:
            y, m = y - 1, 12
        else:
            m -= 1
    # Mid-month so we don't fight with weekends / today's day-of-month.
    day = min(15, monthrange(y, m)[1])
    return date(y, m, day)


async def test_dining_drifts_up_quarter_over_quarter() -> None:
    """12 monthly dining charges. The last 3 average significantly more
    than the prior 9 -> QoQ drift card."""
    today = date.today()
    cat = Category(id="cat-dining", name="Dining out")
    txns: list[Transaction] = []
    for i in range(12, 3, -1):
        txns.append(_txn(_month_anchor(today, i), cat.id, -23000))
    for i in range(3, 0, -1):
        txns.append(_txn(_month_anchor(today, i), cat.id, -31000))
    snapshot = _snapshot([cat], txns)
    insights = await CategoryDriftGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    payload = insights[0].structured_data
    assert payload["comparison_kind"] == "quarter_over_quarter"
    assert payload["direction"] == "up"


async def test_tax_prep_uses_yoy_not_qoq() -> None:
    """Tax prep happens every March: a single $400 charge once per year.
    Under QoQ this looks like a 100% drift up in Q1 vs the quiet Q4.
    YoY comparison sees both years' Q1 land within tolerance.

    Build 24 months. One charge in month_anchor(today, 14) (~last March)
    and one in month_anchor(today, 2) (this March). Both ~$400. YoY drift
    is near zero -> no card."""
    today = date.today()
    cat = Category(id="cat-tax", name="Tax prep")
    txns = [
        _txn(_month_anchor(today, 14), cat.id, -40000),
        _txn(_month_anchor(today, 2), cat.id, -42000),
    ]
    snapshot = _snapshot([cat], txns)
    insights = await CategoryDriftGenerator().run(snapshot, anthropic_key=None)
    assert insights == [], (
        "Annual seasonal category with stable YoY spend must not fire a drift card"
    )


async def test_short_history_skipped() -> None:
    """A category with 4 months of data is skipped — Spending Anomaly
    handles short windows; Category Drift needs at least 12 months."""
    today = date.today()
    cat = Category(id="cat-new", name="New Category")
    txns = [
        _txn(_month_anchor(today, 4), cat.id, -10000),
        _txn(_month_anchor(today, 3), cat.id, -12000),
        _txn(_month_anchor(today, 2), cat.id, -15000),
        _txn(_month_anchor(today, 1), cat.id, -25000),
    ]
    snapshot = _snapshot([cat], txns)
    insights = await CategoryDriftGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_below_dollar_floor_skipped() -> None:
    """Drift pct crosses 15% but trail-prior delta is below $50/mo."""
    today = date.today()
    cat = Category(id="cat-small", name="Tiny")
    txns: list[Transaction] = []
    for i in range(12, 3, -1):
        txns.append(_txn(_month_anchor(today, i), cat.id, -10000))  # $100/mo
    for i in range(3, 0, -1):
        txns.append(_txn(_month_anchor(today, i), cat.id, -12000))  # $120/mo
    snapshot = _snapshot([cat], txns)
    insights = await CategoryDriftGenerator().run(snapshot, anthropic_key=None)
    # 20% drift up but only $20/mo absolute -> below the $50 floor.
    assert insights == []
