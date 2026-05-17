"""Query helpers for the read API."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import Transaction
from app.schemas import TransactionResponse


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
