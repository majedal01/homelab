"""Build a deterministic `YnabSnapshot` for demo mode.

Output is realistic enough to exercise every generator without crossing
into either uncanny-valley fakeness or PII concerns. Numbers are
hard-coded; no RNG. The same bytes ship to every demo visitor.

Naming convention: payees and categories are real names of common
products / services so the UI looks plausible at first glance. Amounts
are in cents.

The snapshot anchors to "today" so date-relative aggregations (drift
windows, weekly anomaly buckets) keep working as the calendar advances.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from app.snapshot.models import (
    Account,
    Category,
    Payee,
    Transaction,
    YnabSnapshot,
)


def build_demo_snapshot(today: date | None = None) -> YnabSnapshot:
    """Top-level builder. `today` override exists for tests."""
    anchor = today or date.today()
    return YnabSnapshot(
        budget_id="demo-budget",
        budget_name="Demo Budget",
        currency_iso="USD",
        fetched_at=datetime.now(UTC),
        accounts=_accounts(),
        categories=_categories(anchor),
        payees=_payees(),
        transactions=_transactions(anchor),
    )


# --- accounts ---------------------------------------------------------------


def _accounts() -> list[Account]:
    return [
        Account(
            id="acc-checking",
            name="Checking",
            type="checking",
            on_budget=True,
            closed=False,
            balance_cents=4_215_00,
        ),
        Account(
            id="acc-savings",
            name="Savings",
            type="savings",
            on_budget=True,
            closed=False,
            balance_cents=18_540_00,
        ),
        Account(
            id="acc-credit",
            name="Credit Card",
            type="creditCard",
            on_budget=True,
            closed=False,
            balance_cents=-1_286_00,
        ),
        Account(
            id="acc-401k",
            name="401(k)",
            type="otherAsset",
            on_budget=False,
            closed=False,
            balance_cents=42_310_00,
        ),
    ]


# --- categories -------------------------------------------------------------


@dataclass(frozen=True)
class _CatDef:
    id: str
    name: str
    goal_target_cents: int | None = None
    goal_overall_left_cents: int | None = None
    goal_percentage_complete: int | None = None
    goal_months_to_budget: int | None = None
    goal_type: str | None = None


def _category_defs() -> list[_CatDef]:
    return [
        _CatDef("cat-rta", "Inflow: Ready to Assign"),
        _CatDef("cat-rent", "Rent"),
        _CatDef("cat-groceries", "Groceries"),
        _CatDef("cat-dining", "Dining out"),
        _CatDef("cat-coffee", "Coffee"),
        _CatDef("cat-subs", "Subscriptions"),
        _CatDef("cat-utilities", "Utilities"),
        _CatDef("cat-phone", "Phone"),
        _CatDef("cat-gas", "Gas"),
        _CatDef("cat-rideshare", "Rideshare"),
        _CatDef("cat-travel", "Travel"),
        _CatDef("cat-shopping", "Shopping"),
        _CatDef("cat-health", "Health"),
        _CatDef("cat-gifts", "Gifts"),
        _CatDef("cat-charity", "Charity"),
        _CatDef(
            "cat-emergency",
            "Emergency Fund",
            goal_target_cents=10_000_00,
            goal_overall_left_cents=3_500_00,
            goal_percentage_complete=65,
            goal_months_to_budget=7,
            goal_type="TB",
        ),
        _CatDef(
            "cat-vacation",
            "Vacation Fund",
            goal_target_cents=5_000_00,
            goal_overall_left_cents=2_100_00,
            goal_percentage_complete=58,
            goal_months_to_budget=5,
            goal_type="TBD",
        ),
        _CatDef(
            "cat-laptop",
            "New Laptop",
            goal_target_cents=2_500_00,
            goal_overall_left_cents=300_00,
            goal_percentage_complete=88,
            goal_months_to_budget=2,
            goal_type="TB",
        ),
    ]


def _categories(today: date) -> list[Category]:
    out: list[Category] = []
    for d in _category_defs():
        out.append(
            Category(
                id=d.id,
                name=d.name,
                hidden=False,
                goal_type=d.goal_type,
                goal_target_cents=d.goal_target_cents,
                goal_target_month=(today.replace(day=1) + timedelta(days=210))
                if d.goal_target_cents
                else None,
                goal_percentage_complete=d.goal_percentage_complete,
                goal_overall_left_cents=d.goal_overall_left_cents,
                goal_months_to_budget=d.goal_months_to_budget,
            )
        )
    return out


# --- payees -----------------------------------------------------------------


def _payees() -> list[Payee]:
    return [
        Payee(id="p-employer", name="Employer Direct Deposit"),
        Payee(id="p-landlord", name="Greystar Apartments"),
        Payee(id="p-wholefoods", name="Whole Foods"),
        Payee(id="p-trader", name="Trader Joe's"),
        Payee(id="p-costco", name="Costco"),
        Payee(id="p-chipotle", name="Chipotle"),
        Payee(id="p-thai", name="Thai Garden"),
        Payee(id="p-starbucks", name="Starbucks"),
        Payee(id="p-blue-bottle", name="Blue Bottle Coffee"),
        Payee(id="p-spotify", name="Spotify"),
        Payee(id="p-netflix", name="Netflix"),
        Payee(id="p-nyt", name="New York Times"),
        Payee(id="p-claude", name="Anthropic"),
        Payee(id="p-pge", name="PG&E"),
        Payee(id="p-comcast", name="Comcast"),
        Payee(id="p-att", name="AT&T"),
        Payee(id="p-shell", name="Shell"),
        Payee(id="p-uber", name="Uber"),
        Payee(id="p-lyft", name="Lyft"),
        Payee(id="p-airbnb", name="Airbnb"),
        Payee(id="p-united", name="United Airlines"),
        Payee(id="p-amazon", name="Amazon"),
        Payee(id="p-target", name="Target"),
        Payee(id="p-rei", name="REI"),
        Payee(id="p-kaiser", name="Kaiser Permanente"),
        # Transfer payee for the credit-card-payment leg.
        Payee(id="p-xfer-cc", name="Transfer: Credit Card", transfer_account_id="acc-credit"),
    ]


# --- transactions -----------------------------------------------------------


def _transactions(today: date) -> list[Transaction]:
    """Build ~14 months of activity, anchored to `today`.

    Patterns we seed deliberately:
    - Monthly paycheck (income to RTA)
    - Monthly rent
    - Weekly groceries (with a spike in the current week to trigger Spending Anomaly)
    - 4 monthly subscriptions (Subscription Audit)
    - Dining + coffee day-of-week patterns
    - Two travel events in the last 6 months
    - Dining drift up ~35% in the trailing quarter (Category Drift)
    - Monthly contributions to the three goal categories
    """
    txns: list[Transaction] = []
    earliest = today - timedelta(days=420)
    cur = earliest

    week_idx = 0
    while cur <= today:
        # --- monthly cadence -----------------------------------------------
        if cur.day == 1:
            # Paycheck (1st of month, $4,800)
            txns.append(_txn("pay", cur, 4_800_00, "acc-checking", "p-employer", "cat-rta", None))
            # Rent
            txns.append(
                _txn("rent", cur, -1_650_00, "acc-checking", "p-landlord", "cat-rent", None)
            )
            # Subscriptions (lined up on the 1st for the demo so they cluster cleanly)
            txns.append(_txn("spt", cur, -11_99, "acc-credit", "p-spotify", "cat-subs", None))
            txns.append(_txn("nflx", cur, -15_49, "acc-credit", "p-netflix", "cat-subs", None))
            txns.append(_txn("nyt", cur, -25_00, "acc-credit", "p-nyt", "cat-subs", None))
            txns.append(_txn("clde", cur, -20_00, "acc-credit", "p-claude", "cat-subs", None))
            # Goal contributions
            txns.append(
                _txn("e", cur, -500_00, "acc-checking", None, "cat-emergency", "to emergency")
            )
            txns.append(
                _txn("v", cur, -300_00, "acc-checking", None, "cat-vacation", "to vacation")
            )
            txns.append(_txn("lap", cur, -150_00, "acc-checking", None, "cat-laptop", "to laptop"))
            # Utilities
            txns.append(_txn("pge", cur, -85_00, "acc-checking", "p-pge", "cat-utilities", None))
            txns.append(
                _txn("com", cur, -69_99, "acc-checking", "p-comcast", "cat-utilities", None)
            )
            txns.append(_txn("att", cur, -55_00, "acc-checking", "p-att", "cat-phone", None))
            # Credit card payment (transfer out of checking; the transfer payee
            # has transfer_account_id=acc-credit so it's an on-budget-to-on-budget
            # transfer that the snapshot/queries layer excludes from Income vs Expense.
            txns.append(_txn("cc", cur, -800_00, "acc-checking", "p-xfer-cc", None, "CC payment"))

        # --- weekly cadence -------------------------------------------------
        if cur.weekday() == 5:  # Saturday
            week_idx += 1
            # Groceries (usually $90-130). Spike to $310 in the current ISO week
            # to trigger Spending Anomaly.
            iso_today = today.isocalendar()
            iso_cur = cur.isocalendar()
            same_week = iso_today.year == iso_cur.year and iso_today.week == iso_cur.week
            base = 310_00 if same_week else (95_00 if (week_idx % 2) else 125_00)
            payee = "p-wholefoods" if (week_idx % 3) else "p-trader"
            txns.append(
                _txn(f"gr{week_idx}", cur, -base, "acc-credit", payee, "cat-groceries", None)
            )

        # --- dining + coffee weekday patterns -------------------------------
        if cur.weekday() in (1, 4):  # Tue + Fri
            # Dining: drifts up ~35% in the trailing quarter
            months_ago = _months_between(cur, today)
            is_trailing_quarter = 1 <= months_ago <= 3
            base = 38_00 if is_trailing_quarter else 28_00
            payee = "p-chipotle" if (cur.day % 2 == 0) else "p-thai"
            txns.append(
                _txn(f"din-{cur.isoformat()}", cur, -base, "acc-credit", payee, "cat-dining", None)
            )
        if cur.weekday() in (0, 2, 4):  # M, W, F
            payee = "p-starbucks" if (cur.day % 2 == 0) else "p-blue-bottle"
            txns.append(
                _txn(f"cf-{cur.isoformat()}", cur, -6_50, "acc-credit", payee, "cat-coffee", None)
            )

        # --- ad hoc shopping / gas (light) ----------------------------------
        if cur.day in (8, 22):
            txns.append(
                _txn(
                    f"shop-{cur.isoformat()}",
                    cur,
                    -125_00,
                    "acc-credit",
                    "p-amazon",
                    "cat-shopping",
                    None,
                )
            )
        if cur.day == 17:
            txns.append(
                _txn(
                    f"gas-{cur.isoformat()}", cur, -55_00, "acc-credit", "p-shell", "cat-gas", None
                )
            )
        if cur.day == 20 and cur.month % 3 == 0:
            txns.append(
                _txn(
                    f"ride-{cur.isoformat()}",
                    cur,
                    -28_00,
                    "acc-credit",
                    "p-uber",
                    "cat-rideshare",
                    None,
                )
            )

        cur += timedelta(days=1)

    # --- travel events (one ~4 months ago, one ~7 months ago) ---------------
    for months_back, scale in ((4, 1.0), (7, 0.8)):
        evt_date = today - timedelta(days=months_back * 30)
        txns.append(
            _txn(
                f"flight-{months_back}",
                evt_date,
                int(-485_00 * scale),
                "acc-credit",
                "p-united",
                "cat-travel",
                "round trip",
            )
        )
        txns.append(
            _txn(
                f"stay-{months_back}",
                evt_date + timedelta(days=2),
                int(-620_00 * scale),
                "acc-credit",
                "p-airbnb",
                "cat-travel",
                None,
            )
        )

    # --- one big-ticket health expense (for Year-in-Money biggest-single) ---
    txns.append(
        _txn(
            "dr-ann",
            today - timedelta(days=50),
            -812_00,
            "acc-credit",
            "p-kaiser",
            "cat-health",
            "annual physical",
        )
    )

    # Sort newest first to match the live snapshot's ordering invariant.
    txns.sort(key=lambda t: (t.date, t.id), reverse=True)
    return txns


def _txn(
    suffix: str,
    when: date,
    amount_cents: int,
    account_id: str,
    payee_id: str | None,
    category_id: str | None,
    memo: str | None,
) -> Transaction:
    return Transaction(
        id=f"t-{suffix}-{when.isoformat()}",
        date=when,
        amount_cents=amount_cents,
        account_id=account_id,
        payee_id=payee_id,
        category_id=category_id,
        memo=memo,
    )


def _months_between(earlier: date, later: date) -> int:
    """Approximate months between (later - earlier). Positive when earlier < later."""
    return (later.year - earlier.year) * 12 + (later.month - earlier.month)
