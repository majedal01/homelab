"""Subscription Audit (v2.6h).

Each test builds a deterministic snapshot and runs the generator under
asyncio. We never call the LLM; passing `anthropic_key=None` makes
enhance_copy fall back to the deterministic title/summary.

v2.6h gates every candidate on a positive subscription signal (a
subscription-like category/group name, or a known-merchant payee) plus
exclusions (transfers, bills/debt/insurance/tax categories, special
payees). Recurrence-focused tests therefore file their charges under a
"Subscriptions" category so the clustering logic still gets exercised.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.insights.subscription_audit import SubscriptionAuditGenerator, _normalize_payee
from app.snapshot.models import Account, Category, Payee, Transaction, YnabSnapshot

CHECKING = Account(
    id="acct-1",
    name="Checking",
    type="checking",
    on_budget=True,
    closed=False,
    balance_cents=100000,
)

# Default category gives charges a positive subscription signal so the
# recurrence/cadence tests below exercise clustering rather than the gate.
SUBS_CAT = Category(
    id="cat-subs",
    name="Subscriptions",
    category_group_name="Lifestyle",
)


def _snapshot(
    payees: list[Payee],
    txns: list[Transaction],
    *,
    accounts: list[Account] | None = None,
    categories: list[Category] | None = None,
) -> YnabSnapshot:
    return YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=accounts if accounts is not None else [CHECKING],
        categories=categories if categories is not None else [SUBS_CAT],
        payees=payees,
        transactions=txns,
    )


def _txn(
    d: date,
    payee_id: str | None,
    amount: int,
    *,
    category_id: str | None = "cat-subs",
    **kw: Any,
) -> Transaction:
    return Transaction(
        id=f"t-{payee_id}-{d.isoformat()}-{amount}",
        date=d,
        amount_cents=amount,
        account_id="acct-1",
        payee_id=payee_id,
        category_id=category_id,
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
    v2.6f's amount tolerance keeps them together."""
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
    band, so no subscription card even with a subscription category."""
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


async def test_yearly_cadence_with_two_occurrences_within_band() -> None:
    """One annual charge, two consecutive years (365 days apart). Filed
    under a subscription category so the signal gate lets it through."""
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


# --- v2.6h: subscription signal gate ---------------------------------------


async def test_detected_via_merchant_allowlist_without_category() -> None:
    """A known merchant (Hulu) is detected even with no category, via the
    merchant allowlist path."""
    payees = [Payee(id="p-hulu", name="Hulu")]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=60), "p-hulu", -1799, category_id=None),
        _txn(today - timedelta(days=30), "p-hulu", -1799, category_id=None),
        _txn(today, "p-hulu", -1799, category_id=None),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["payee_name"] == "Hulu"


async def test_detected_via_category_keyword_unknown_merchant() -> None:
    """An unknown merchant filed under a 'Subscriptions' category is still
    detected via the category-signal path."""
    payees = [Payee(id="p-local", name="Neighborhood Yoga Studio")]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=60), "p-local", -3000),
        _txn(today - timedelta(days=30), "p-local", -3000),
        _txn(today, "p-local", -3000),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1


async def test_recurring_non_subscription_merchant_is_ignored() -> None:
    """A recurring restaurant charge (unknown merchant, no subscription
    category) has no positive signal and must not produce a card, even
    though it clusters cleanly."""
    payees = [Payee(id="p-chi", name="Chipotle")]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=60), "p-chi", -1500, category_id="cat-food"),
        _txn(today - timedelta(days=30), "p-chi", -1500, category_id="cat-food"),
        _txn(today, "p-chi", -1500, category_id="cat-food"),
    ]
    food = Category(id="cat-food", name="Eating Out", category_group_name="Lifestyle")
    snapshot = _snapshot(payees, txns, categories=[food])
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_bill_category_excluded_even_for_known_merchant() -> None:
    """Exclusions win over the positive signal: a charge filed under a
    Rent/Mortgage category is dropped regardless of recurrence."""
    payees = [Payee(id="p-rent", name="Landlord LLC")]
    today = date.today()
    rent = Category(id="cat-rent", name="Rent/Mortgage", category_group_name="Essentials")
    txns = [
        _txn(today - timedelta(days=60), "p-rent", -150000, category_id="cat-rent"),
        _txn(today - timedelta(days=30), "p-rent", -150000, category_id="cat-rent"),
        _txn(today, "p-rent", -150000, category_id="cat-rent"),
    ]
    snapshot = _snapshot(payees, txns, categories=[rent])
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


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
        _txn(today - timedelta(days=90), "p-xfer", -50000, category_id=None),
        _txn(today - timedelta(days=60), "p-xfer", -50000, category_id=None),
        _txn(today - timedelta(days=30), "p-xfer", -50000, category_id=None),
        _txn(today, "p-xfer", -50000, category_id=None),
    ]
    snapshot = _snapshot(
        [transfer_payee], txns, accounts=[CHECKING, savings], categories=[SUBS_CAT]
    )
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_off_budget_transfer_debt_payment_excluded() -> None:
    """A recurring transfer to an OFF-budget loan account is a debt
    payment, not a subscription. Even a category signal must not rescue
    it — the transfer exclusion covers all transfer destinations."""
    loan_payee = Payee(id="p-loan", name="Transfer : Auto Loan", transfer_account_id="acct-loan")
    loan = Account(
        id="acct-loan",
        name="Auto Loan",
        type="autoLoan",
        on_budget=False,
        closed=False,
        balance_cents=-2000000,
    )
    today = date.today()
    txns = [
        _txn(today - timedelta(days=90), "p-loan", -50000),
        _txn(today - timedelta(days=60), "p-loan", -50000),
        _txn(today - timedelta(days=30), "p-loan", -50000),
        _txn(today, "p-loan", -50000),
    ]
    snapshot = _snapshot([loan_payee], txns, accounts=[CHECKING, loan], categories=[SUBS_CAT])
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_special_payee_excluded() -> None:
    """Reconciliation Balance Adjustment recurs but is bookkeeping, not a
    subscription."""
    payees = [Payee(id="p-rec", name="Reconciliation Balance Adjustment")]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=60), "p-rec", -5000),
        _txn(today - timedelta(days=30), "p-rec", -5000),
        _txn(today, "p-rec", -5000),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_null_payee_dropped() -> None:
    """A recurring charge with no payee (merchant only in the memo) is
    dropped — v2.6h confirmed real subs always carry a payee, so there is
    no memo-fallback clustering."""
    today = date.today()
    txns = [
        _txn(today - timedelta(days=60), None, -1099, memo="NETFLIX"),
        _txn(today - timedelta(days=30), None, -1099, memo="NETFLIX"),
        _txn(today, None, -1099, memo="NETFLIX"),
    ]
    snapshot = _snapshot([], txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


# --- v2.6f/g regression coverage: prior versions returned zero on these ----


async def test_price_hike_produces_two_clusters_not_zero() -> None:
    """Spotify $9.99 for 5 months, then $11.99 for 3 months. v2.6g
    sub-clusters by amount so each price-band fires its own card."""
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
    """Real monthly billing posts at 28-34 days. The cadence band (25-35)
    is the only spacing check."""
    payees = [Payee(id="p-gym", name="Gym")]
    today = date.today()
    txns = [
        _txn(today - timedelta(days=34), "p-gym", -3500),
        _txn(today, "p-gym", -3500),
    ]
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["cadence"] == "monthly"


async def test_five_distinct_subscription_patterns_all_detected() -> None:
    """One run, five qualifying subscriptions of different shapes — all
    filed under a subscription category so nothing falls through."""
    today = date.today()
    payees = [
        Payee(id="p-nf", name="Netflix"),
        Payee(id="p-nf2", name="NETFLIX.COM"),
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
    # 3. Monthly with 28-34d jitter: AWS posts vary on weekends
    for offset in (180, 152, 118, 87, 56, 28):
        txns.append(_txn(today - timedelta(days=offset), "p-aws", -4500))
    # 4. Quarterly at $30 (3 occurrences)
    for offset in (270, 180, 90):
        txns.append(_txn(today - timedelta(days=offset), "p-tax", -3000))
    snapshot = _snapshot(payees, txns)
    insights = await SubscriptionAuditGenerator().run(snapshot, anthropic_key=None)
    # Spotify-$9.99, Spotify-$11.99, Netflix, AWS, TurboTax-quarterly
    assert len(insights) >= 5, f"Detected only {len(insights)}: {[i.title for i in insights]}"


async def test_outlier_amount_doesnt_kill_the_whole_cluster() -> None:
    """If one charge is wildly off (promo month) and the rest are tight,
    the cluster still qualifies."""
    payees = [Payee(id="p-x", name="Spotify")]
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
    assert any(i.structured_data["amount_cents"] == 1499 for i in insights)
