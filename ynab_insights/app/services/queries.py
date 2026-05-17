"""Query helpers for the read API and dashboard views."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.sql import Select

from app.models import Account, Budget, Category, Payee, Transaction
from app.schemas import TransactionResponse
from app.services.cache import TTLCache

# Single shared cache instance for the dashboard's hot queries. 30-second TTL
# matches our default sync cadence well enough that fresh syncs are visible
# within a couple of dashboard refreshes.
_spending_cache: TTLCache[list["CategorySpend"]] = TTLCache(ttl_seconds=30.0)


def _exclude_transfers[T: Select[Any]](stmt: T) -> T:
    """Filter out transactions whose payee represents the other side of an
    account-to-account transfer. YNAB models transfers as paired transactions
    pointing at a synthetic payee whose `transfer_account_id` is set; those
    are operational movements of money, not spending or income."""
    transfer_payee = (
        select(Payee.id)
        .where(Payee.id == Transaction.payee_id, Payee.transfer_account_id.is_not(None))
        .exists()
    )
    return stmt.where(~transfer_payee)


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
    """Sum of negative-amount transactions in [start, end] grouped by category,
    excluding account-to-account transfers. Outflows stay negative so callers
    can render with their own sign convention."""
    stmt = (
        select(
            Category.id,
            Category.name,
            func.coalesce(func.sum(Transaction.amount_cents), 0).label("total"),
        )
        .select_from(Transaction)
        .outerjoin(Category, Category.id == Transaction.category_id)
        .where(
            Transaction.budget_id == budget_id,
            Transaction.date >= start,
            Transaction.date <= end,
            Transaction.amount_cents < 0,
        )
        .group_by(Category.id, Category.name)
        .order_by("total")  # most-negative first = highest spend first
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
    """Period summary used by the agent's `monthly_summary` tool."""
    from calendar import monthrange

    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    base = (
        Transaction.budget_id == budget_id,
        Transaction.date >= start,
        Transaction.date <= end,
    )

    inflow_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            *base, Transaction.amount_cents > 0
        )
    )
    outflow_stmt = _exclude_transfers(
        select(func.coalesce(func.sum(Transaction.amount_cents), 0)).where(
            *base, Transaction.amount_cents < 0
        )
    )
    count_stmt = _exclude_transfers(select(func.count()).select_from(Transaction).where(*base))
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
        date=t.date,
        amount_cents=t.amount_cents,
        memo=t.memo,
        cleared=t.cleared,
        approved=t.approved,
    )
