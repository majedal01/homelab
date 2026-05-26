"""Category Projection (v2.6g).

Projects this month's spending forward from MTD pace, compares against
trailing-12-month average. Tests cover:

- Top categories produce projection cards when pace diverges materially
- Early-month skip prevents single-purchase noise from projecting absurdly
- Below-threshold delta doesn't fire
- Categories with no baseline get rejected (no historical data)
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from typing import Any
from unittest.mock import patch

from app.insights.category_projection import CategoryProjectionGenerator
from app.snapshot.models import Account, Category, Transaction, YnabSnapshot

CHECKING = Account(
    id="acct-1",
    name="Checking",
    type="checking",
    on_budget=True,
    closed=False,
    balance_cents=500000,
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


def _midmonth_today() -> date:
    """A date guaranteed to be at least MIN_DAYS_INTO_MONTH (5) into its
    calendar month. Picks the 15th of today's month or last month."""
    today = date.today()
    if today.day >= 15:
        return date(today.year, today.month, 15)
    # Today is before mid-month — pick the 15th of last month.
    if today.month == 1:
        return date(today.year - 1, 12, 15)
    return date(today.year, today.month - 1, 15)


async def test_overspending_category_fires_projection() -> None:
    """Category spending $400 in 15 days vs $300/mo baseline -> projected
    ~$800 month-end, way over the 15% delta threshold."""
    pinned_today = _midmonth_today()
    cat = Category(id="cat-dining", name="Dining")
    txns: list[Transaction] = []
    # 12 months of $300/mo baseline (ending before this month)
    for months_back in range(12, 0, -1):
        anchor = pinned_today
        y, m = anchor.year, anchor.month
        for _ in range(months_back):
            if m == 1:
                y, m = y - 1, 12
            else:
                m -= 1
        # Drop $300 in that month
        txns.append(_txn(date(y, m, 15), cat.id, -30000))
    # This month: $400 by day 15
    txns.append(_txn(date(pinned_today.year, pinned_today.month, 5), cat.id, -10000))
    txns.append(_txn(date(pinned_today.year, pinned_today.month, 10), cat.id, -15000))
    txns.append(_txn(date(pinned_today.year, pinned_today.month, 14), cat.id, -15000))
    snapshot = _snapshot([cat], txns)
    with patch("app.insights.category_projection.date") as mock_date:
        mock_date.today.return_value = pinned_today
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        insights = await CategoryProjectionGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    payload = insights[0].structured_data
    assert payload["direction"] == "over"
    assert payload["category_id"] == cat.id


async def test_early_month_skipped() -> None:
    """Days 1-4 of month: too noisy. No card."""
    cat = Category(id="cat-x", name="X")
    today = date.today()
    pinned = date(today.year, today.month, 1) if today.day > 1 else today
    if pinned.day > 4:
        # Today's already past the skip window; can't construct this test
        # without time travel. Use last month's day-3 anchor instead.
        if pinned.month == 1:
            pinned = date(pinned.year - 1, 12, 3)
        else:
            pinned = date(pinned.year, pinned.month - 1, 3)
    txns = [_txn(pinned, cat.id, -50000)]
    snapshot = _snapshot([cat], txns)
    with patch("app.insights.category_projection.date") as mock_date:
        mock_date.today.return_value = pinned
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        insights = await CategoryProjectionGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_below_threshold_no_card() -> None:
    """Projected delta below both 15% and $50 floors -> no card."""
    pinned_today = _midmonth_today()
    cat = Category(id="cat-y", name="Y")
    txns: list[Transaction] = []
    # Baseline: $1000/mo. MTD at $500 with 15 days in: pace -> $1000 in a
    # 30-day month. Exactly on baseline.
    days_in_month = monthrange(pinned_today.year, pinned_today.month)[1]
    mtd_for_match = int(round(1000_00 * pinned_today.day / days_in_month))
    for months_back in range(12, 0, -1):
        y, m = pinned_today.year, pinned_today.month
        for _ in range(months_back):
            if m == 1:
                y, m = y - 1, 12
            else:
                m -= 1
        txns.append(_txn(date(y, m, 15), cat.id, -100000))
    txns.append(_txn(date(pinned_today.year, pinned_today.month, 5), cat.id, -mtd_for_match))
    snapshot = _snapshot([cat], txns)
    with patch("app.insights.category_projection.date") as mock_date:
        mock_date.today.return_value = pinned_today
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        insights = await CategoryProjectionGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_no_baseline_no_card() -> None:
    """Category with only this-month activity -> no baseline -> no card."""
    pinned_today = _midmonth_today()
    cat = Category(id="cat-new", name="Brand new category")
    txns = [_txn(date(pinned_today.year, pinned_today.month, 10), cat.id, -50000)]
    snapshot = _snapshot([cat], txns)
    with patch("app.insights.category_projection.date") as mock_date:
        mock_date.today.return_value = pinned_today
        mock_date.side_effect = lambda *args, **kw: date(*args, **kw)
        insights = await CategoryProjectionGenerator().run(snapshot, anthropic_key=None)
    assert insights == []
