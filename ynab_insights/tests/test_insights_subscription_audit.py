"""Subscription Audit (v2.6f).

Each test builds a deterministic snapshot and runs the generator under
asyncio. We never call the LLM; passing `anthropic_key=None` makes
enhance_copy fall back to the deterministic title/summary.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.insights.subscription_audit import SubscriptionAuditGenerator, _normalize_payee
from app.snapshot.models import Account, Payee, Transaction, YnabSnapshot

CHECKING = Account(
    id="acct-1",
    name="Checking",
    type="checking",
    on_budget=True,
    closed=False,
    balance_cents=100000,
)


def _snapshot(
    payees: list[Payee],
    txns: list[Transaction],
) -> YnabSnapshot:
    return YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=[CHECKING],
        categories=[],
        payees=payees,
        transactions=txns,
    )


def _txn(d: date, payee_id: str, amount: int, **kw: Any) -> Transaction:
    return Transaction(
        id=f"t-{payee_id}-{d.isoformat()}",
        date=d,
        amount_cents=amount,
        account_id="acct-1",
        payee_id=payee_id,
        **kw,
    )


def test_normalize_payee_collapses_common_variants() -> None:
    """All variants of "Netflix" YNAB might emit should normalize alike."""
    base = _normalize_payee("Netflix")
    assert base == "netflix"
    assert _normalize_payee("NETFLIX") == base
    assert _normalize_payee("NETFLIX.COM") == base
    assert _normalize_payee("Netflix Inc.") == base
    assert _normalize_payee("PAYPAL *NETFLIX") == base
    assert _normalize_payee("NETFLIX 4839A2NX") == base
    # Distinct merchants must still differ.
    assert _normalize_payee("Spotify") != base


async def test_netflix_with_midwindow_price_change_clusters() -> None:
    """Five monthly Netflix charges, price goes from $15.99 to $17.99
    halfway through. v2.4 split this into two never-qualifying clusters;
    v2.6f's 12% amount tolerance keeps them together."""
    payees = [Payee(id="p-nf", name="Netflix")]
    today = date.today()
    dates = [today - timedelta(days=30 * i) for i in range(5, 0, -1)]
    txns = [
        _txn(dates[0], "p-nf", -1599),
        _txn(dates[1], "p-nf", -1599),
        _txn(dates[2], "p-nf", -1799),
        _txn(dates[3], "p-nf", -1799),
        _txn(dates[4], "p-nf", -1799),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    payload = insights[0].structured_data
    assert payload["cadence"] == "monthly"
    assert payload["amount_cents"] in (1599, 1799), payload["amount_cents"]


async def test_two_tight_occurrences_qualify() -> None:
    """Two charges, exactly 30d apart, identical amount: counts as
    monthly under the relaxed minimum-occurrences rule."""
    payees = [Payee(id="p-spo", name="Spotify")]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=30), "p-spo", -1099),
        _txn(today, "p-spo", -1099),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["cadence"] == "monthly"


async def test_two_loose_occurrences_do_not_qualify() -> None:
    """Two charges 45 days apart — interval is outside every cadence
    band, so no subscription card."""
    payees = [Payee(id="p-x", name="Random Service")]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=75), "p-x", -1099),
        _txn(today - timedelta(days=30), "p-x", -1099),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_payee_normalization_clusters_variants() -> None:
    """Two YNAB payee_ids that map to the same merchant ('Netflix' and
    'NETFLIX.COM') cluster into a single subscription card."""
    payees = [
        Payee(id="p-a", name="Netflix"),
        Payee(id="p-b", name="NETFLIX.COM"),
    ]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=90), "p-a", -1799),
        _txn(today - timedelta(days=60), "p-b", -1799),
        _txn(today - timedelta(days=30), "p-a", -1799),
        _txn(today, "p-b", -1799),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["cadence"] == "monthly"


async def test_internal_transfer_excluded() -> None:
    """Recurring transfer to a savings account looks subscription-shaped
    but must not produce a card."""
    transfer_payee = Payee(
        id="p-xfer", name="Transfer : Savings", transfer_account_id="acct-savings"
    )
    savings = Account(
        id="acct-savings",
        name="Savings",
        type="savings",
        on_budget=True,
        closed=False,
        balance_cents=0,
    )
    today = date.today()
    txns = [
        _txn(today - timedelta(days=90), "p-xfer", -50000),
        _txn(today - timedelta(days=60), "p-xfer", -50000),
        _txn(today - timedelta(days=30), "p-xfer", -50000),
        _txn(today, "p-xfer", -50000),
    ]
    snapshot = YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=[CHECKING, savings],
        categories=[],
        payees=[transfer_payee],
        transactions=txns,
    )
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_yearly_cadence_with_two_occurrences_within_band() -> None:
    """One annual charge, two consecutive years (365 days apart)."""
    payees = [Payee(id="p-tax", name="TurboTax")]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=365), "p-tax", -10000),
        _txn(today, "p-tax", -10000),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["cadence"] == "yearly"
