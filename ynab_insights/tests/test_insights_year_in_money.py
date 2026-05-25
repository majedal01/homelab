"""Year in Money (v2.6f).

Calendar-anchored triggers are gone: any session with at least 90 days
of data gets a card, annual or quarterly depending on history span.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.insights.year_in_money import YearInMoneyGenerator
from app.snapshot.models import Account, Category, Transaction, YnabSnapshot

CHECKING = Account(
    id="acct-1",
    name="Checking",
    type="checking",
    on_budget=True,
    closed=False,
    balance_cents=100000,
)
GROC = Category(id="cat-groc", name="Groceries")
INCOME_CAT = Category(id="cat-inc", name="Inflow: Ready to Assign")


def _txn(d: date, amount: int, cat_id: str = GROC.id, **kw: Any) -> Transaction:
    return Transaction(
        id=f"t-{cat_id}-{d.isoformat()}-{amount}",
        date=d,
        amount_cents=amount,
        account_id="acct-1",
        category_id=cat_id,
        **kw,
    )


def _snapshot(txns: list[Transaction]) -> YnabSnapshot:
    return YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=[CHECKING],
        categories=[GROC, INCOME_CAT],
        payees=[],
        transactions=txns,
    )


async def test_annual_card_fires_with_a_year_of_data() -> None:
    today = date.today()
    txns: list[Transaction] = []
    for week in range(53):
        d = today - timedelta(days=7 * week)
        txns.append(_txn(d, -5000))
    # Income, so savings_rate isn't null
    txns.append(_txn(today - timedelta(days=30), 400_000, cat_id=INCOME_CAT.id))
    snapshot = _snapshot(txns)
    insights = await YearInMoneyGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    payload = insights[0].structured_data
    assert payload["period_kind"] == "annual"
    assert payload["period_label"] == "last 12 months"


async def test_quarterly_card_fires_when_only_three_months_of_data() -> None:
    today = date.today()
    txns: list[Transaction] = []
    for week in range(13):
        d = today - timedelta(days=7 * week)
        txns.append(_txn(d, -5000))
    txns.append(_txn(today - timedelta(days=20), 80_000, cat_id=INCOME_CAT.id))
    snapshot = _snapshot(txns)
    insights = await YearInMoneyGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    payload = insights[0].structured_data
    assert payload["period_kind"] == "quarterly"
    assert payload["period_label"] == "last 90 days"


async def test_no_card_when_under_90_days() -> None:
    today = date.today()
    txns = [_txn(today - timedelta(days=30), -5000)]
    snapshot = _snapshot(txns)
    insights = await YearInMoneyGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_no_card_when_no_transactions() -> None:
    snapshot = _snapshot([])
    insights = await YearInMoneyGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_dedup_key_includes_kind_and_end_month() -> None:
    """The dedup key should let the card refresh once per month (window
    rolls forward) without churn within the same month."""
    today = date.today()
    txns = [_txn(today - timedelta(days=7 * w), -5000) for w in range(53)]
    txns.append(_txn(today - timedelta(days=30), 400_000, cat_id=INCOME_CAT.id))
    snapshot = _snapshot(txns)
    insights = await YearInMoneyGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    key = insights[0].dedup_key
    assert key.startswith("year_in_money:b1:annual:")
    assert key.endswith(today.strftime("%Y-%m"))
