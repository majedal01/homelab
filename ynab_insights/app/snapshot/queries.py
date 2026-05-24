"""In-memory aggregations over `YnabSnapshot`.

These mirror `app/services/queries.py` but operate on a single budget's
Pydantic snapshot held in the session cache. No SQL, no DB session.

Semantic parity with the SQL versions:
- "Income vs Expense" treats positives in null-category-or-RTA as income,
  and everything categorized (except RTA) as spending.
- Transfers between two on-budget accounts are excluded. Categorized legs
  of a transfer to OFF-budget (e.g. car loan payment) stay as spending.
- Closed accounts are NOT filtered out for historical aggregates: YNAB's
  reports include them, so we do too.
"""

from __future__ import annotations

from calendar import monthrange
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.snapshot.models import Transaction, YnabSnapshot

# YNAB's built-in income category. Pre-2022 budgets used the legacy name.
INCOME_CATEGORY_NAMES = frozenset(
    {
        "Inflow: Ready to Assign",
        "Inflow: To Be Budgeted",
    }
)
INCOME_CATEGORY_NAME = "Inflow: Ready to Assign"


# --- shared filters ---------------------------------------------------------


def _on_budget_account_ids(snapshot: YnabSnapshot) -> set[str]:
    return {a.id for a in snapshot.accounts if a.on_budget}


def _internal_transfer_payee_ids(snapshot: YnabSnapshot) -> set[str]:
    """Payees that represent a transfer to an on-budget account.

    These are the "internal" transfers YNAB excludes from Income vs Expense.
    Transfers to off-budget accounts (loan payments, investment buys) keep
    their categorized leg as spending.
    """
    on_budget = _on_budget_account_ids(snapshot)
    return {
        p.id
        for p in snapshot.payees
        if p.transfer_account_id is not None and p.transfer_account_id in on_budget
    }


def _is_excluded_transfer(
    txn: Transaction,
    internal_payee_ids: set[str],
) -> bool:
    return txn.payee_id is not None and txn.payee_id in internal_payee_ids


def _is_income_category(category_name: str | None) -> bool:
    return category_name is not None and category_name in INCOME_CATEGORY_NAMES


# --- aggregations -----------------------------------------------------------


@dataclass(frozen=True)
class CategorySpend:
    category_id: str | None
    category_name: str | None
    spent_cents: int  # negative when net outflow


def spending_by_category(
    snapshot: YnabSnapshot,
    start: date,
    end: date,
) -> list[CategorySpend]:
    """Net category spending over [start, end]. Sorted most-negative first.

    Excludes income categories, internal transfers, and off-budget
    accounts. Reimbursements categorized to the same category cancel out
    (net is preserved, not absolute outflow).
    """
    on_budget = _on_budget_account_ids(snapshot)
    transfers = _internal_transfer_payee_ids(snapshot)
    cat_by_id = snapshot.category_by_id()

    sums: dict[str | None, int] = defaultdict(int)
    name_by_id: dict[str | None, str | None] = {}
    for t in snapshot.transactions:
        if t.account_id not in on_budget:
            continue
        if not (start <= t.date <= end):
            continue
        if _is_excluded_transfer(t, transfers):
            continue
        if t.category_id is None:
            continue
        cat = cat_by_id.get(t.category_id)
        if cat is None or _is_income_category(cat.name):
            continue
        sums[t.category_id] += t.amount_cents
        name_by_id[t.category_id] = cat.name

    out: list[CategorySpend] = []
    for cat_id, total in sums.items():
        if total >= 0:
            continue  # net refund or zero: not spending
        out.append(
            CategorySpend(
                category_id=cat_id,
                category_name=name_by_id[cat_id],
                spent_cents=total,
            )
        )
    out.sort(key=lambda r: r.spent_cents)  # most negative first
    return out


@dataclass(frozen=True)
class PeriodSummary:
    date_from: date
    date_to: date
    income_cents: int  # positive
    spending_cents: int  # positive
    net_income_cents: int  # income - spending
    transaction_count: int
    by_category: list[CategoryNet]


@dataclass(frozen=True)
class CategoryNet:
    category_id: str | None
    category_name: str | None
    net_cents: int  # negative = net outflow


def period_summary(
    snapshot: YnabSnapshot,
    start: date,
    end: date,
) -> PeriodSummary:
    """YNAB-style Income vs Expense rollup for [start, end]."""
    on_budget = _on_budget_account_ids(snapshot)
    transfers = _internal_transfer_payee_ids(snapshot)
    cat_by_id = snapshot.category_by_id()

    income = 0
    spending = 0
    count = 0
    cat_nets: dict[str | None, int] = defaultdict(int)
    cat_names: dict[str | None, str | None] = {}

    for t in snapshot.transactions:
        if t.account_id not in on_budget:
            continue
        if not (start <= t.date <= end):
            continue
        if _is_excluded_transfer(t, transfers):
            continue
        count += 1

        cat = cat_by_id.get(t.category_id) if t.category_id else None
        cat_name = cat.name if cat else None
        is_income_row = t.amount_cents > 0 and (
            t.category_id is None or _is_income_category(cat_name)
        )
        if is_income_row:
            income += t.amount_cents
            continue
        if t.category_id is None:
            continue
        if _is_income_category(cat_name):
            continue
        spending += -t.amount_cents  # accumulate as positive
        cat_nets[t.category_id] += t.amount_cents
        cat_names[t.category_id] = cat_name

    by_category = sorted(
        (
            CategoryNet(category_id=cid, category_name=cat_names[cid], net_cents=net)
            for cid, net in cat_nets.items()
        ),
        key=lambda r: r.net_cents,
    )
    return PeriodSummary(
        date_from=start,
        date_to=end,
        income_cents=income,
        spending_cents=spending,
        net_income_cents=income - spending,
        transaction_count=count,
        by_category=by_category,
    )


@dataclass(frozen=True)
class CategoryMonthlyHistory:
    category_id: str
    category_name: str
    monthly_nets_cents: list[int]  # oldest first, length == months


def category_monthly_history(
    snapshot: YnabSnapshot,
    months: int,
) -> list[CategoryMonthlyHistory]:
    """Per-category monthly nets over the trailing `months` months.

    Only categories with any expense activity in the window are returned.
    Income categories and internal transfers are excluded.
    """
    if months <= 0:
        return []

    starts = _month_starts_back(date.today(), months)
    window_start = starts[0]
    window_end = date(
        starts[-1].year,
        starts[-1].month,
        monthrange(starts[-1].year, starts[-1].month)[1],
    )

    on_budget = _on_budget_account_ids(snapshot)
    transfers = _internal_transfer_payee_ids(snapshot)
    cat_by_id = snapshot.category_by_id()

    matrix: dict[str, dict[tuple[int, int], int]] = defaultdict(lambda: defaultdict(int))
    names: dict[str, str] = {}

    for t in snapshot.transactions:
        if t.account_id not in on_budget:
            continue
        if not (window_start <= t.date <= window_end):
            continue
        if _is_excluded_transfer(t, transfers):
            continue
        if t.category_id is None:
            continue
        cat = cat_by_id.get(t.category_id)
        if cat is None or _is_income_category(cat.name):
            continue
        matrix[t.category_id][(t.date.year, t.date.month)] += t.amount_cents
        names[t.category_id] = cat.name

    return [
        CategoryMonthlyHistory(
            category_id=cid,
            category_name=names[cid],
            monthly_nets_cents=[matrix[cid].get((d.year, d.month), 0) for d in starts],
        )
        for cid in matrix
    ]


def transactions_in_range(
    snapshot: YnabSnapshot,
    date_from: date,
    date_to: date,
) -> list[Transaction]:
    """All transactions in [date_from, date_to]. Newest-first ordering
    preserved from snapshot.transactions."""
    return [t for t in snapshot.transactions if date_from <= t.date <= date_to]


def starting_balance_cents(snapshot: YnabSnapshot) -> int:
    """Sum of open on-budget account balances. The base for cashflow projections."""
    return sum(
        a.balance_cents
        for a in snapshot.accounts
        if a.on_budget and not a.closed
    )


# --- helpers ----------------------------------------------------------------


def _month_starts_back(today: date, n: int) -> list[date]:
    """First-of-month dates for the last `n` months ending in `today`'s month,
    oldest first."""
    out: list[date] = []
    year, month = today.year, today.month
    for _ in range(n):
        out.append(date(year, month, 1))
        if month == 1:
            year, month = year - 1, 12
        else:
            month -= 1
    out.reverse()
    return out
