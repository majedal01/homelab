"""Per-category cycle classifier (v2.6f).

The classifier feeds Spending Anomaly and Category Drift, so the
fixtures here mimic categories those generators care about:

- Rent: monthly, tight intervals
- Groceries: weekly via frequency floor (lots of small charges)
- Property tax: annual, two occurrences ~year apart
- Random Etsy: one purchase, no detectable pattern -> irregular

`today` is pinned per-test so the windows are reproducible.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.snapshot.cycle import classify_category_cycle
from app.snapshot.models import Account, Category, Payee, Transaction, YnabSnapshot

TODAY = date(2026, 5, 25)
CHECKING = Account(
    id="acct-1",
    name="Checking",
    type="checking",
    on_budget=True,
    closed=False,
    balance_cents=500000,
)
RENT = Category(id="cat-rent", name="Rent")
GROC = Category(id="cat-groc", name="Groceries")
TAX = Category(id="cat-tax", name="Property Tax")
ETSY = Category(id="cat-etsy", name="Hobbies")


def _snapshot(txns: list[Transaction], cats: list[Category]) -> YnabSnapshot:
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


def _txn(d: date, cat_id: str, amount: int = -50000, **kw: Any) -> Transaction:
    return Transaction(
        id=f"t-{cat_id}-{d.isoformat()}",
        date=d,
        amount_cents=amount,
        account_id="acct-1",
        category_id=cat_id,
        **kw,
    )


def test_monthly_rent() -> None:
    """Monthly on the 1st, 12 occurrences, tight intervals."""
    txns = [_txn(date(2025, m, 1), RENT.id, amount=-150000) for m in range(6, 13)]
    txns += [_txn(date(2026, m, 1), RENT.id, amount=-150000) for m in range(1, 6)]
    result = classify_category_cycle(_snapshot(txns, [RENT]), RENT.id, today=TODAY)
    assert result.cycle == "monthly"
    assert result.occurrences == 12
    assert result.median_interval_days is not None and 28 <= result.median_interval_days <= 32


def test_weekly_groceries_via_frequency_floor() -> None:
    """Groceries: 3 txns/wk, varying amounts. Classified weekly via the
    frequency floor before interval inspection."""
    txns = []
    cur = TODAY - timedelta(days=300)
    while cur < TODAY:
        for offset in (0, 2, 5):
            txns.append(_txn(cur + timedelta(days=offset), GROC.id, amount=-7000 - offset * 100))
        cur += timedelta(days=7)
    assert len(txns) > 40, "fixture must clear the frequency floor"
    result = classify_category_cycle(_snapshot(txns, [GROC]), GROC.id, today=TODAY)
    assert result.cycle == "weekly"


def test_annual_property_tax() -> None:
    """Property tax: two occurrences ~365d apart. Classified annual via
    the extended 18-month window."""
    txns = [
        _txn(date(2024, 11, 15), TAX.id, amount=-450000),
        _txn(date(2025, 11, 14), TAX.id, amount=-460000),
    ]
    result = classify_category_cycle(_snapshot(txns, [TAX]), TAX.id, today=TODAY)
    assert result.cycle == "annual"
    assert result.occurrences == 2


def test_single_etsy_purchase_is_irregular() -> None:
    """One transaction in 12 months, none earlier — no signal."""
    txns = [_txn(date(2026, 3, 11), ETSY.id, amount=-8000)]
    result = classify_category_cycle(_snapshot(txns, [ETSY]), ETSY.id, today=TODAY)
    assert result.cycle == "irregular"


def test_noisy_intervals_fall_back_to_irregular() -> None:
    """Same monthly category but the user paid twice mid-month sometimes;
    interval CoV blows past the regularity threshold."""
    dates = [
        date(2025, 6, 1),
        date(2025, 6, 18),
        date(2025, 7, 2),
        date(2025, 8, 15),
        date(2025, 9, 30),
        date(2025, 11, 10),
        date(2026, 2, 1),
        date(2026, 3, 4),
    ]
    txns = [_txn(d, RENT.id, amount=-50000) for d in dates]
    result = classify_category_cycle(_snapshot(txns, [RENT]), RENT.id, today=TODAY)
    assert result.cycle == "irregular"


def test_internal_transfers_are_excluded() -> None:
    """A transfer-payee transaction in the category must not count
    toward the cycle classifier."""
    transfer_payee = Payee(id="p-xfer", name="Transfer", transfer_account_id="acct-savings")
    savings = Account(
        id="acct-savings",
        name="Savings",
        type="savings",
        on_budget=True,
        closed=False,
        balance_cents=100000,
    )
    txns = [
        _txn(date(2026, 1, 1), RENT.id, amount=-150000),
        _txn(date(2026, 1, 15), RENT.id, amount=-150000, payee_id="p-xfer"),
        _txn(date(2026, 2, 1), RENT.id, amount=-150000),
    ]
    snap = YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=[CHECKING, savings],
        categories=[RENT],
        payees=[transfer_payee],
        transactions=txns,
    )
    result = classify_category_cycle(snap, RENT.id, today=TODAY)
    # Two real occurrences in 12 months -> irregular by recent-window but
    # may trigger annual fallback; assert it didn't count the transfer.
    assert result.occurrences == 2
