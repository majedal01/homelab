"""Query helpers for the read API and dashboard views."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, joinedload
from sqlalchemy.sql import Select

from app.models import Account, Budget, Category, Payee, Transaction
from app.schemas import TransactionResponse
from app.services.cache import TTLCache

# YNAB ships a single built-in income category. Income transactions are
# categorized to it instead of having a null category, so spending/income
# aggregates have to treat it specially. The name has changed across YNAB
# versions; budgets created before 2022 still use the legacy variant.
INCOME_CATEGORY_NAMES = frozenset(
    {
        "Inflow: Ready to Assign",  # current
        "Inflow: To Be Budgeted",  # legacy (pre-2022 budgets)
    }
)
# Kept as a single string for backwards compat with imports elsewhere.
INCOME_CATEGORY_NAME = "Inflow: Ready to Assign"

# Single shared cache instance for the dashboard's hot queries. 30-second TTL
# matches our default sync cadence well enough that fresh syncs are visible
# within a couple of dashboard refreshes.
_spending_cache: TTLCache[list["CategorySpend"]] = TTLCache(ttl_seconds=30.0)


def _exclude_transfers[T: Select[Any]](stmt: T) -> T:
    """Filter out true on-budget-to-on-budget transfers.

    YNAB pairs transfers with a synthetic payee whose `transfer_account_id`
    points at the OTHER account. A transfer is "internal" (and excluded
    from the Income vs. Expense report) only when both accounts are
    on-budget. When the other side is OFF-budget (loans, investments,
    tracking accounts), YNAB treats the categorized leg as real spending
    — paying down a car loan is a Car Payment expense even though it's
    posted as a transfer.

    Earlier this filter excluded ALL transfer-payee rows, which dropped
    legitimate categorized outflows like the Car Payment example.
    """
    transfer_target = aliased(Account)
    transfer_to_on_budget = (
        select(Payee.id)
        .join(transfer_target, transfer_target.id == Payee.transfer_account_id)
        .where(
            Payee.id == Transaction.payee_id,
            transfer_target.on_budget.is_(True),
        )
        .exists()
    )
    return stmt.where(~transfer_to_on_budget)


@dataclass(frozen=True)
class CategorySpend:
    category_id: str | None
    category_name: str | None
    spent_cents: int  # negative; sum of transaction amount_cents where < 0


async def list_budgets_ordered(session: AsyncSession) -> Sequence[Budget]:
    """All budgets sorted by name. For nav and budget switcher."""
    result = await session.execute(select(Budget).order_by(Budget.name))
    return result.scalars().all()


async def list_open_accounts(session: AsyncSession, budget_id: str) -> Sequence[Account]:
    """Non-closed accounts for a budget, sorted by name."""
    stmt = (
        select(Account)
        .where(Account.budget_id == budget_id, Account.closed.is_(False))
        .order_by(Account.name)
    )
    result = await session.execute(stmt)
    return result.scalars().all()


async def spending_by_category(
    session: AsyncSession,
    budget_id: str,
    start: date,
    end: date,
) -> list[CategorySpend]:
    """Net spending per category over [start, end], scoped to on-budget
    accounts and excluding transfers + the YNAB income category.

    Sums BOTH inflows and outflows per category so that reimbursements
    posted to the same category (e.g. "Reimbursable Expenses" with the
    expense as outflow + employer payment as inflow) cancel out. Returns
    only categories with net outflow (sum < 0); categories that net to
    refund or zero are omitted from the spending view. The built-in
    `Inflow: Ready to Assign` category is excluded entirely since it's
    income, not spending.

    `spent_cents` stays negative (= sum of amount_cents for the category)
    so existing callers that flip the sign for display keep working.
    """
    # Note: we deliberately do NOT filter `Account.closed.is_(False)` here.
    # YNAB's Income vs. Expense report includes historical transactions on
    # accounts the user has since closed, so excluding them would
    # under-report spending for the month a closure happened in.
    stmt = (
        select(
            Category.id,
            Category.name,
            func.coalesce(func.sum(Transaction.amount_cents), 0).label("total"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            Transaction.budget_id == budget_id,
            Transaction.date >= start,
            Transaction.date <= end,
            Account.on_budget.is_(True),
            Category.name.notin_(INCOME_CATEGORY_NAMES),
        )
        .group_by(Category.id, Category.name)
        .having(func.coalesce(func.sum(Transaction.amount_cents), 0) < 0)
        .order_by("total")  # most-negative first = highest net spend first
    )
    stmt = _exclude_transfers(stmt)
    result = await session.execute(stmt)
    return [
        CategorySpend(category_id=row.id, category_name=row.name, spent_cents=int(row.total))
        for row in result.all()
    ]


async def list_transactions(
    session: AsyncSession,
    *,
    budget_id: str | None = None,
    account_id: str | None = None,
    category_id: str | None = None,
    payee_id: str | None = None,
    payee_name_contains: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[Transaction]:
    """Fetch transactions with related entities eagerly loaded so callers can
    build name-embedded responses without N+1 queries.

    `payee_name_contains` performs a case-insensitive substring match on the
    payee name (used by the agent for natural-language payee lookups).
    """
    stmt = (
        select(Transaction)
        .options(
            joinedload(Transaction.account),
            joinedload(Transaction.category),
            joinedload(Transaction.payee),
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    )
    if budget_id is not None:
        stmt = stmt.where(Transaction.budget_id == budget_id)
    if account_id is not None:
        stmt = stmt.where(Transaction.account_id == account_id)
    if category_id is not None:
        stmt = stmt.where(Transaction.category_id == category_id)
    if payee_id is not None:
        stmt = stmt.where(Transaction.payee_id == payee_id)
    if payee_name_contains is not None:
        stmt = stmt.join(Payee, Payee.id == Transaction.payee_id).where(
            Payee.name.ilike(f"%{payee_name_contains}%")
        )
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    stmt = stmt.limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().all()


@dataclass(frozen=True)
class MonthSummary:
    year: int
    month: int
    total_inflow_cents: int
    total_outflow_cents: int
    transaction_count: int
    top_categories: list[CategorySpend]  # top 5 by spend


async def monthly_summary(
    session: AsyncSession,
    budget_id: str,
    year: int,
    month: int,
) -> MonthSummary:
    """Period summary matching YNAB's "Income vs. Expense" report semantics:

    - Inflow ("Total Income"): positive-amount rows in a null category on an
      on-budget account, transfers excluded. Refunds posted to expense
      categories are NOT income — they reduce that category's net spend.
    - Outflow ("Total Expenses"): sum of all amounts on categorized rows on
      on-budget accounts, transfers excluded. Returned as a non-positive
      number so callers preserve the historical sign convention. A category
      that nets to a refund (Education +$156) reduces total expenses, which
      is exactly what YNAB does.
    """
    from calendar import monthrange

    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    # Closed accounts intentionally NOT filtered out: YNAB's Income vs.
    # Expense report includes historical transactions on accounts the user
    # has since closed.
    base = (
        Transaction.budget_id == budget_id,
        Transaction.date >= start,
        Transaction.date <= end,
        Account.on_budget.is_(True),
    )

    # YNAB income lives in the built-in "Inflow: Ready to Assign" category;
    # treat positive amounts tagged to it as income, and exclude it from the
    # expense rollup so it doesn't get counted as negative spending.
    inflow_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0))
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            *base,
            Transaction.amount_cents > 0,
            or_(
                Transaction.category_id.is_(None),
                Category.name.in_(INCOME_CATEGORY_NAMES),
            ),
        )
    )
    outflow_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0))
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            *base,
            Transaction.category_id.is_not(None),
            Category.name.notin_(INCOME_CATEGORY_NAMES),
        )
    )
    count_stmt = _exclude_transfers(
        select(func.count())
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(*base)
    )
    inflow = (await session.execute(inflow_stmt)).scalar_one()
    outflow = (await session.execute(outflow_stmt)).scalar_one()
    count = (await session.execute(count_stmt)).scalar_one()

    all_cats = await spending_by_category(session, budget_id, start, end)
    return MonthSummary(
        year=year,
        month=month,
        total_inflow_cents=int(inflow),
        total_outflow_cents=int(outflow),
        transaction_count=int(count),
        top_categories=all_cats[:5],
    )


@dataclass(frozen=True)
class CategoryNet:
    category_id: str | None
    category_name: str | None
    net_cents: int  # negative = net outflow, positive = net refund


@dataclass(frozen=True)
class IncomeSource:
    payee_id: str | None
    payee_name: str | None
    amount_cents: int  # positive total for the period


@dataclass(frozen=True)
class PeriodSummary:
    date_from: date
    date_to: date
    income_cents: int  # YNAB "Total Income"
    spending_cents: int  # YNAB "Total Expenses" as a positive number
    net_income_cents: int  # income - spending
    transaction_count: int
    by_category: list[CategoryNet]  # signed nets per expense category
    by_income_source: list[IncomeSource]  # income broken out by payee
    # Diagnostics: ALL on-budget non-transfer activity, regardless of
    # category. Used by the reconciliation page to surface what's hiding
    # in null-category buckets when the YNAB-style totals don't tie out.
    gross_outflow_cents: int  # sum of every negative amount, positive number
    gross_inflow_cents: int  # sum of every positive amount
    uncategorized_outflow_cents: int  # negatives with category_id=null
    uncategorized_inflow_cents: int  # positives with category_id=null


async def period_summary(
    session: AsyncSession,
    budget_id: str,
    start: date,
    end: date,
) -> PeriodSummary:
    """One-shot YNAB-style "Income vs. Expense" rollup for a date range.

    Used as the single source of truth for the dashboard's KPI tiles and
    the donut card. Computing both from the same SQL guarantees the
    "This month spending" KPI and the donut total stay consistent — and
    that they match the categories page's "Total in range".

    Semantics match YNAB's Income vs. Expense report:
    - Income: positive amounts where category is null OR one of the
      built-in income categories (`Inflow: Ready to Assign` / legacy
      `Inflow: To Be Budgeted`).
    - Spending: net of all amounts on rows tagged to a non-income
      category. Refunds posted to an expense category reduce its net
      (and therefore reduce total spending).
    - On-budget accounts only; transfers excluded.
    """
    # Closed accounts intentionally NOT excluded — see monthly_summary for
    # the rationale (YNAB's Income vs. Expense report includes them).
    base_filter = (
        Transaction.budget_id == budget_id,
        Transaction.date >= start,
        Transaction.date <= end,
        Account.on_budget.is_(True),
    )

    income_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0))
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            *base_filter,
            Transaction.amount_cents > 0,
            or_(
                Transaction.category_id.is_(None),
                Category.name.in_(INCOME_CATEGORY_NAMES),
            ),
        )
    )
    spending_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(-Transaction.amount_cents), 0))
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            *base_filter,
            Transaction.category_id.is_not(None),
            Category.name.notin_(INCOME_CATEGORY_NAMES),
        )
    )
    count_stmt = _exclude_transfers(
        select(func.count())
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(*base_filter)
    )
    by_category_stmt = _exclude_transfers(
        select(
            Category.id,
            Category.name,
            func.coalesce(func.sum(Transaction.amount_cents), 0).label("net"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            *base_filter,
            Transaction.category_id.is_not(None),
            Category.name.notin_(INCOME_CATEGORY_NAMES),
        )
        .group_by(Category.id, Category.name)
        .order_by("net")
    )
    by_payee_stmt = _exclude_transfers(
        select(
            Payee.id,
            Payee.name,
            func.coalesce(func.sum(Transaction.amount_cents), 0).label("amount"),
        )
        .select_from(Transaction)
        .outerjoin(Payee, Payee.id == Transaction.payee_id)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            *base_filter,
            Transaction.amount_cents > 0,
            or_(
                Transaction.category_id.is_(None),
                Category.name.in_(INCOME_CATEGORY_NAMES),
            ),
        )
        .group_by(Payee.id, Payee.name)
        .order_by(func.sum(Transaction.amount_cents).desc())
    )
    gross_outflow_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(-Transaction.amount_cents), 0))
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(*base_filter, Transaction.amount_cents < 0)
    )
    gross_inflow_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0))
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(*base_filter, Transaction.amount_cents > 0)
    )
    uncat_outflow_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(-Transaction.amount_cents), 0))
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            *base_filter,
            Transaction.amount_cents < 0,
            Transaction.category_id.is_(None),
        )
    )
    uncat_inflow_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0))
        .select_from(Transaction)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            *base_filter,
            Transaction.amount_cents > 0,
            Transaction.category_id.is_(None),
        )
    )

    income = (await session.execute(income_stmt)).scalar_one()
    spending = (await session.execute(spending_stmt)).scalar_one()
    count = (await session.execute(count_stmt)).scalar_one()
    by_cat_rows = (await session.execute(by_category_stmt)).all()
    by_payee_rows = (await session.execute(by_payee_stmt)).all()
    gross_outflow = (await session.execute(gross_outflow_stmt)).scalar_one()
    gross_inflow = (await session.execute(gross_inflow_stmt)).scalar_one()
    uncat_outflow = (await session.execute(uncat_outflow_stmt)).scalar_one()
    uncat_inflow = (await session.execute(uncat_inflow_stmt)).scalar_one()

    income_int = int(income)
    spending_int = int(spending)
    return PeriodSummary(
        date_from=start,
        date_to=end,
        income_cents=income_int,
        spending_cents=spending_int,
        net_income_cents=income_int - spending_int,
        transaction_count=int(count),
        by_category=[
            CategoryNet(
                category_id=row.id,
                category_name=row.name,
                net_cents=int(row.net),
            )
            for row in by_cat_rows
        ],
        by_income_source=[
            IncomeSource(
                payee_id=row.id,
                payee_name=row.name,
                amount_cents=int(row.amount),
            )
            for row in by_payee_rows
        ],
        gross_outflow_cents=int(gross_outflow),
        gross_inflow_cents=int(gross_inflow),
        uncategorized_outflow_cents=int(uncat_outflow),
        uncategorized_inflow_cents=int(uncat_inflow),
    )


@dataclass(frozen=True)
class CategoryMonthlyHistory:
    """Per-category history of monthly nets over the lookback window."""

    category_id: str
    category_name: str
    # Oldest first. Each entry is the net for one calendar month, in cents.
    monthly_nets_cents: list[int]


async def category_monthly_history(
    session: AsyncSession,
    budget_id: str,
    months: int,
) -> list[CategoryMonthlyHistory]:
    """Per-category monthly net spending across the trailing `months`
    calendar months ending in the current month, oldest first.

    Backs the Category Drift generator. Issues one query per month —
    same shape as `monthly_trend` — so it's portable across Postgres
    and SQLite without dialect-specific date-part functions.
    """
    from calendar import monthrange

    if months <= 0:
        return []

    starts = _month_starts_back(date.today(), months)

    # Discover the expense categories that had any activity in the window
    # so we don't return a row for every category in the budget.
    overall_stmt = _exclude_transfers(
        select(Category.id, Category.name)
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .join(Account, Account.id == Transaction.account_id)
        .where(
            Transaction.budget_id == budget_id,
            Transaction.date >= starts[0],
            Transaction.date
            <= date(
                starts[-1].year, starts[-1].month, monthrange(starts[-1].year, starts[-1].month)[1]
            ),
            Transaction.category_id.is_not(None),
            Category.name.notin_(INCOME_CATEGORY_NAMES),
            Account.on_budget.is_(True),
        )
        .group_by(Category.id, Category.name)
    )
    active = (await session.execute(overall_stmt)).all()
    if not active:
        return []

    matrix: dict[str, dict[tuple[int, int], int]] = {row.id: {} for row in active}
    names: dict[str, str] = {row.id: row.name for row in active}

    for ms in starts:
        me = date(ms.year, ms.month, monthrange(ms.year, ms.month)[1])
        per_cat_stmt = _exclude_transfers(
            select(
                Category.id,
                func.coalesce(func.sum(Transaction.amount_cents), 0).label("net"),
            )
            .select_from(Transaction)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.date >= ms,
                Transaction.date <= me,
                Transaction.category_id.is_not(None),
                Category.name.notin_(INCOME_CATEGORY_NAMES),
                Account.on_budget.is_(True),
            )
            .group_by(Category.id)
        )
        for row in (await session.execute(per_cat_stmt)).all():
            if row.id in matrix:
                matrix[row.id][(ms.year, ms.month)] = int(row.net)

    return [
        CategoryMonthlyHistory(
            category_id=cat_id,
            category_name=names[cat_id],
            monthly_nets_cents=[matrix[cat_id].get((ms.year, ms.month), 0) for ms in starts],
        )
        for cat_id in matrix
    ]


async def cached_spending_by_category(
    session: AsyncSession,
    budget_id: str,
    start: date,
    end: date,
) -> list[CategorySpend]:
    """Cached wrapper for the dashboard route. Tests of the underlying
    aggregation use `spending_by_category` directly to bypass the cache."""
    key = ("spending", budget_id, start.isoformat(), end.isoformat())
    cached = _spending_cache.get(key)
    if cached is not None:
        return cached
    result = await spending_by_category(session, budget_id, start, end)
    _spending_cache.set(key, result)
    return result


def _month_starts_back(today: date, n: int) -> list[date]:
    """List the first-of-month dates for the last `n` months ending in
    `today`'s month, oldest first."""
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


async def monthly_outflows(
    session: AsyncSession,
    budget_id: str,
    months: int = 6,
) -> list[tuple[date, int]]:
    """Total outflow (negative cents) for each of the last `months` calendar
    months, oldest first. Transfers excluded via `_exclude_transfers`."""
    from calendar import monthrange

    results: list[tuple[date, int]] = []
    for ms in _month_starts_back(date.today(), months):
        me = date(ms.year, ms.month, monthrange(ms.year, ms.month)[1])
        stmt = _exclude_transfers(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
                Transaction.budget_id == budget_id,
                Transaction.date >= ms,
                Transaction.date <= me,
                Transaction.amount_cents < 0,
            )
        )
        outflow = (await session.execute(stmt)).scalar_one()
        results.append((ms, int(outflow)))
    return results


@dataclass(frozen=True)
class MonthlyTrendRow:
    year: int
    month: int
    spending_cents: int  # positive: total outflow for the month
    income_cents: int  # positive: total inflow for the month


async def monthly_trend(
    session: AsyncSession,
    budget_id: str,
    months: int,
) -> list[MonthlyTrendRow]:
    """Spending + income aggregated per calendar month, oldest first.

    Scoped to on-budget accounts and excludes transfers, matching the
    dashboard's KPI definitions. Issues one SQL roundtrip per month — same
    pattern as `monthly_outflows` — so it works identically on Postgres
    (prod) and SQLite (tests) without needing dialect-specific date-part
    functions. Response size is bounded by `months`, fixing the prior
    client-side rollup that hit the `/transactions?limit=500` cap.
    """
    from calendar import monthrange

    if months <= 0:
        return []

    results: list[MonthlyTrendRow] = []
    for ms in _month_starts_back(date.today(), months):
        me = date(ms.year, ms.month, monthrange(ms.year, ms.month)[1])
        # Closed accounts intentionally NOT excluded — their historical
        # rows belong in the trend chart for months when the account was
        # still active.
        base_filter = (
            Transaction.budget_id == budget_id,
            Transaction.date >= ms,
            Transaction.date <= me,
            Account.on_budget.is_(True),
        )
        # Spending matches YNAB's "Total Expenses": net of all amounts on
        # categorized rows, excluding the built-in income category. Refunds
        # in expense categories reduce the total.
        spending_stmt = _exclude_transfers(
            select(func.coalesce(func.sum(-Transaction.amount_cents), 0))
            .select_from(Transaction)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                *base_filter,
                Transaction.category_id.is_not(None),
                Category.name.notin_(INCOME_CATEGORY_NAMES),
            )
        )
        # Income matches YNAB's "Total Income": positive amounts where the
        # category is null OR one of the built-in income categories.
        income_stmt = _exclude_transfers(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0))
            .select_from(Transaction)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                *base_filter,
                Transaction.amount_cents > 0,
                or_(
                    Transaction.category_id.is_(None),
                    Category.name.in_(INCOME_CATEGORY_NAMES),
                ),
            )
        )
        spending = (await session.execute(spending_stmt)).scalar_one()
        income = (await session.execute(income_stmt)).scalar_one()
        results.append(
            MonthlyTrendRow(
                year=ms.year,
                month=ms.month,
                spending_cents=int(spending),
                income_cents=int(income),
            )
        )
    return results


async def list_categories_for_budget(
    session: AsyncSession, budget_id: str | None
) -> Sequence[Category]:
    stmt = select(Category).order_by(Category.name)
    if budget_id is not None:
        stmt = stmt.where(Category.budget_id == budget_id)
    return (await session.execute(stmt)).scalars().all()


async def list_accounts_for_budget(
    session: AsyncSession, budget_id: str | None
) -> Sequence[Account]:
    stmt = select(Account).where(Account.closed.is_(False)).order_by(Account.name)
    if budget_id is not None:
        stmt = stmt.where(Account.budget_id == budget_id)
    return (await session.execute(stmt)).scalars().all()


def transaction_to_response(t: Transaction) -> TransactionResponse:
    """Build a name-embedded response from a Transaction with relationships loaded."""
    return TransactionResponse(
        id=t.id,
        budget_id=t.budget_id,
        account_id=t.account_id,
        account_name=t.account.name,
        category_id=t.category_id,
        category_name=t.category.name if t.category else None,
        payee_id=t.payee_id,
        payee_name=t.payee.name if t.payee else None,
        transfer_account_id=t.payee.transfer_account_id if t.payee else None,
        date=t.date,
        amount_cents=t.amount_cents,
        memo=t.memo,
        cleared=t.cleared,
        approved=t.approved,
    )
