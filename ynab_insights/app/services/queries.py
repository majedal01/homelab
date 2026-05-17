"""Query helpers for the read API and dashboard views."""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Account, Budget, Category, Transaction
from app.schemas import TransactionResponse


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
    """Sum of negative-amount transactions in [start, end] grouped by category.
    Outflows are negative in YNAB; we keep the sign so callers can render."""
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
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> Sequence[Transaction]:
    """Fetch transactions with related entities eagerly loaded so callers can
    build name-embedded responses without N+1 queries."""
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
    if date_from is not None:
        stmt = stmt.where(Transaction.date >= date_from)
    if date_to is not None:
        stmt = stmt.where(Transaction.date <= date_to)
    stmt = stmt.limit(limit).offset(offset)

    result = await session.execute(stmt)
    return result.scalars().all()


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
