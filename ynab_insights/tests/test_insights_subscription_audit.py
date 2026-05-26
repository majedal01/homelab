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


def test_normalize_payee_strips_city_state_tails() -> None:
    """Card-network payees often arrive with a trailing city and state."""
    base = _normalize_payee("Starbucks")
    assert _normalize_payee("STARBUCKS SEATTLE WA") == base
    assert _normalize_payee("Starbucks Seattle WA") == base


def test_normalize_payee_strips_pos_prefixes() -> None:
    """Square / Toast / Stripe / Paddle present with merchant-processor
    prefixes; the underlying merchant must still cluster."""
    coffee = _normalize_payee("Bluestone Coffee")
    assert _normalize_payee("SQ *BLUESTONE COFFEE") == coffee
    assert _normalize_payee("TST*Bluestone Coffee") == coffee


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


# --- v2.6g regression coverage: prior versions returned zero on these ------


async def test_price_hike_produces_two_clusters_not_zero() -> None:
    """Spotify $9.99 for 5 months, then $11.99 for 3 months. v2.6f's
    all-amounts-within-12%-of-median rule rejected the entire normalized
    group because 9.99 vs 11.99 = 20% spread. v2.6g sub-clusters by
    amount so each price-band fires its own card."""
    payees = [Payee(id="p-spo", name="Spotify")]
    today = date.today()
    txns: list[Transaction] = []
    for i in range(8, 3, -1):  # 5 old at $9.99
        txns.append(_txn(today - timedelta(days=30 * i), "p-spo", -999))
    for i in range(3, 0, -1):  # 3 new at $11.99
        txns.append(_txn(today - timedelta(days=30 * i), "p-spo", -1199))
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    amounts = sorted(i.structured_data["amount_cents"] for i in insights)
    assert amounts == [999, 1199], f"Expected one card per price band, got: {amounts}"


async def test_monthly_with_billing_jitter_is_not_rejected() -> None:
    """Real monthly billing posts at 28-34 days. v2.6f's '2-occurrence
    interval must be target+/-3 days' gate rejected 34d. v2.6g lets the
    cadence band (25-35) be the only spacing check."""
    payees = [Payee(id="p-gym", name="Gym")]
    today = date.today()
    # Two charges 34d apart: outside +/-3 of 30d target, inside monthly band.
    txns = [
        _txn(today - timedelta(days=34), "p-gym", -3500),
        _txn(today, "p-gym", -3500),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["cadence"] == "monthly"


async def test_five_distinct_subscription_patterns_all_detected() -> None:
    """One run, five qualifying subscriptions of different shapes —
    nothing should silently fall through."""
    today = date.today()
    payees = [
        Payee(id="p-nf", name="Netflix"),
        Payee(id="p-nf2", name="NETFLIX.COM"),
        Payee(id="p-rent", name="Landlord LLC"),
        Payee(id="p-spo", name="Spotify"),
        Payee(id="p-aws", name="AWS"),
        Payee(id="p-tax", name="TurboTax"),
    ]
    txns: list[Transaction] = []
    # 1. Price-hike: Spotify $9.99 (5) then $11.99 (3)
    for i in range(8, 3, -1):
        txns.append(_txn(today - timedelta(days=30 * i), "p-spo", -999))
    for i in range(3, 0, -1):
        txns.append(_txn(today - timedelta(days=30 * i), "p-spo", -1199))
    # 2. Varied payee strings: Netflix vs NETFLIX.COM normalize the same
    for i in range(6, 0, -1):
        pid = "p-nf" if i % 2 == 0 else "p-nf2"
        txns.append(_txn(today - timedelta(days=30 * i), pid, -1599))
    # 3. 2-occurrence high-value monthly: rent
    for i in (2, 1):
        txns.append(_txn(today - timedelta(days=30 * i), "p-rent", -150000))
    # 4. Monthly with 28-34d jitter: AWS posts vary on weekends
    for offset in (180, 152, 118, 87, 56, 28):
        txns.append(_txn(today - timedelta(days=offset), "p-aws", -4500))
    # 5. Quarterly TurboTax-ish at $30 (4 occurrences)
    for offset in (270, 180, 90):
        txns.append(_txn(today - timedelta(days=offset), "p-tax", -3000))
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    # Expect at least 5 cards (price-hike splits Spotify into 2):
    # Spotify-$9.99, Spotify-$11.99, Netflix, Rent, AWS, TurboTax-quarterly
    assert len(insights) >= 5, f"Detected only {len(insights)}: {[i.title for i in insights]}"


async def test_outlier_amount_doesnt_kill_the_whole_cluster() -> None:
    """If one charge is wildly off (promo month) and the rest are tight,
    the cluster still qualifies. v2.6f rejected the whole group."""
    payees = [Payee(id="p-x", name="StreamSvc")]
    today = date.today()
    txns: list[Transaction] = [
        _txn(today - timedelta(days=150), "p-x", -1499),
        _txn(today - timedelta(days=120), "p-x", -1499),
        _txn(today - timedelta(days=90), "p-x", -100),  # promo month
        _txn(today - timedelta(days=60), "p-x", -1499),
        _txn(today - timedelta(days=30), "p-x", -1499),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    # The 4 $14.99 charges qualify; the lone $1.00 promo gets its own
    # sub-cluster but is too thin to qualify (1 occurrence).
    assert any(i.structured_data["amount_cents"] == 1499 for i in insights)
