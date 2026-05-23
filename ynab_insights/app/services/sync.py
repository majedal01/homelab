"""Sync orchestrator.

Pulls all YNAB entities for every accessible budget and upserts them into the
local database. Upserts use SELECT-then-INSERT-or-UPDATE in Python so the same
code path works against both Postgres (prod) and SQLite (tests).
"""

from __future__ import annotations

import asyncio
import logging

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Budget, Category, Payee, Transaction
from app.services.metrics import counters
from app.services.ynab_client import (
    YNABAccount,
    YNABBudget,
    YNABCategory,
    YNABClient,
    YNABPayee,
    YNABSubTransaction,
    YNABTransaction,
    milliunits_to_cents,
)

logger = logging.getLogger(__name__)

# Module-level lock so the scheduled sync and an ad-hoc `POST /sync` cannot
# run concurrently against the same database. Callers should catch
# `SyncInProgressError` and either skip (scheduler) or surface 409 (HTTP).
_sync_lock = asyncio.Lock()


class SyncInProgressError(RuntimeError):
    """Raised when a sync is already running."""


class SyncResult(BaseModel):
    budgets: int = 0
    accounts: int = 0
    categories: int = 0
    payees: int = 0
    transactions: int = 0


async def run_sync(session: AsyncSession, ynab_token: str) -> SyncResult:
    """Run a full sync of all budgets accessible to the given token.

    Raises SyncInProgressError if another sync is already in flight.
    """
    if _sync_lock.locked():
        raise SyncInProgressError("a sync is already running")
    async with _sync_lock:
        try:
            result = await _do_sync(session, ynab_token)
        except Exception:
            counters.sync_failures += 1
            raise
        counters.sync_runs += 1
        return result


async def _do_sync(session: AsyncSession, ynab_token: str) -> SyncResult:
    result = SyncResult()
    async with YNABClient(ynab_token) as client:
        for budget in await client.list_budgets():
            await _upsert_budget(session, budget)
            result.budgets += 1

            for account in await client.list_accounts(budget.id):
                await _upsert_account(session, account, budget.id)
                result.accounts += 1

            for category in await client.list_categories(budget.id):
                await _upsert_category(session, category, budget.id)
                result.categories += 1

            for payee in await client.list_payees(budget.id):
                await _upsert_payee(session, payee, budget.id)
                result.payees += 1

            # Flush so the categories/payees we just added are visible to the
            # FK-validation queries below.
            await session.flush()
            known_category_ids = await _known_ids(session, Category, budget.id)
            known_payee_ids = await _known_ids(session, Payee, budget.id)

            for txn in await client.list_transactions(budget.id):
                # YNAB returns historical transactions whose category_id or
                # payee_id may reference entities that have since been deleted
                # in YNAB. Those entities are not in the current /categories
                # or /payees responses, so the FK would violate. Nullify the
                # reference and keep the transaction so amounts and dates are
                # still recorded.
                if txn.category_id is not None and txn.category_id not in known_category_ids:
                    logger.info(
                        "nullifying orphan category_id %s on txn %s", txn.category_id, txn.id
                    )
                    txn.category_id = None
                if txn.payee_id is not None and txn.payee_id not in known_payee_ids:
                    logger.info("nullifying orphan payee_id %s on txn %s", txn.payee_id, txn.id)
                    txn.payee_id = None

                if txn.subtransactions:
                    # Split transaction: the parent carries the full amount but
                    # category_id=null. Persist each leg as its own row so the
                    # categorized children show up in reports. Drop any
                    # previously-synced parent row (from before this fix) so
                    # we don't double-count.
                    existing_parent = await session.get(Transaction, txn.id)
                    if existing_parent is not None:
                        await session.delete(existing_parent)
                        await session.flush()
                    for sub in txn.subtransactions:
                        if (
                            sub.category_id is not None
                            and sub.category_id not in known_category_ids
                        ):
                            sub.category_id = None
                        if sub.payee_id is not None and sub.payee_id not in known_payee_ids:
                            sub.payee_id = None
                        await _upsert_subtransaction(session, sub, txn, budget.id)
                        result.transactions += 1
                    continue

                await _upsert_transaction(session, txn, budget.id)
                result.transactions += 1

    await session.commit()
    return result


async def _known_ids(
    session: AsyncSession,
    model: type[Category] | type[Payee],
    budget_id: str,
) -> set[str]:
    rows = await session.execute(select(model.id).where(model.budget_id == budget_id))
    return {row[0] for row in rows.all()}


async def _upsert_budget(session: AsyncSession, source: YNABBudget) -> None:
    currency = "USD"
    if source.currency_format and "iso_code" in source.currency_format:
        currency = str(source.currency_format["iso_code"])

    existing = await session.get(Budget, source.id)
    if existing is None:
        session.add(
            Budget(
                id=source.id,
                name=source.name,
                currency=currency,
                last_modified_on=source.last_modified_on,
            )
        )
    else:
        existing.name = source.name
        existing.currency = currency
        existing.last_modified_on = source.last_modified_on


async def _upsert_account(session: AsyncSession, source: YNABAccount, budget_id: str) -> None:
    existing = await session.get(Account, source.id)
    balance_cents = milliunits_to_cents(source.balance)
    if existing is None:
        session.add(
            Account(
                id=source.id,
                budget_id=budget_id,
                name=source.name,
                type=source.type,
                balance_cents=balance_cents,
                on_budget=source.on_budget,
                closed=source.closed,
            )
        )
    else:
        existing.budget_id = budget_id
        existing.name = source.name
        existing.type = source.type
        existing.balance_cents = balance_cents
        existing.on_budget = source.on_budget
        existing.closed = source.closed


async def _upsert_category(session: AsyncSession, source: YNABCategory, budget_id: str) -> None:
    goal_target_cents = (
        milliunits_to_cents(source.goal_target) if source.goal_target is not None else None
    )
    goal_overall_left_cents = (
        milliunits_to_cents(source.goal_overall_left)
        if source.goal_overall_left is not None
        else None
    )
    existing = await session.get(Category, source.id)
    if existing is None:
        session.add(
            Category(
                id=source.id,
                budget_id=budget_id,
                category_group_id=source.category_group_id,
                name=source.name,
                hidden=source.hidden,
                goal_type=source.goal_type,
                goal_target_cents=goal_target_cents,
                goal_target_month=source.goal_target_month,
                goal_percentage_complete=source.goal_percentage_complete,
                goal_overall_left_cents=goal_overall_left_cents,
                goal_months_to_budget=source.goal_months_to_budget,
            )
        )
    else:
        existing.budget_id = budget_id
        existing.category_group_id = source.category_group_id
        existing.name = source.name
        existing.hidden = source.hidden
        existing.goal_type = source.goal_type
        existing.goal_target_cents = goal_target_cents
        existing.goal_target_month = source.goal_target_month
        existing.goal_percentage_complete = source.goal_percentage_complete
        existing.goal_overall_left_cents = goal_overall_left_cents
        existing.goal_months_to_budget = source.goal_months_to_budget


async def _upsert_payee(session: AsyncSession, source: YNABPayee, budget_id: str) -> None:
    existing = await session.get(Payee, source.id)
    if existing is None:
        session.add(
            Payee(
                id=source.id,
                budget_id=budget_id,
                name=source.name,
                transfer_account_id=source.transfer_account_id,
            )
        )
    else:
        existing.budget_id = budget_id
        existing.name = source.name
        existing.transfer_account_id = source.transfer_account_id


async def _upsert_transaction(
    session: AsyncSession, source: YNABTransaction, budget_id: str
) -> None:
    existing = await session.get(Transaction, source.id)
    amount_cents = milliunits_to_cents(source.amount)
    if existing is None:
        session.add(
            Transaction(
                id=source.id,
                budget_id=budget_id,
                account_id=source.account_id,
                category_id=source.category_id,
                payee_id=source.payee_id,
                date=source.date,
                amount_cents=amount_cents,
                memo=source.memo,
                cleared=source.cleared,
                approved=source.approved,
            )
        )
    else:
        existing.budget_id = budget_id
        existing.account_id = source.account_id
        existing.category_id = source.category_id
        existing.payee_id = source.payee_id
        existing.date = source.date
        existing.amount_cents = amount_cents
        existing.memo = source.memo
        existing.cleared = source.cleared
        existing.approved = source.approved


async def _upsert_subtransaction(
    session: AsyncSession,
    sub: YNABSubTransaction,
    parent: YNABTransaction,
    budget_id: str,
) -> None:
    """Persist one leg of a split as a standalone Transaction row.

    Sub.id is unique in YNAB, so we use it as our primary key. Date,
    account, cleared, and approved come from the parent; category, payee,
    amount, and memo come from the sub itself.
    """
    existing = await session.get(Transaction, sub.id)
    amount_cents = milliunits_to_cents(sub.amount)
    # Sub may omit payee_id, in which case YNAB intends the parent's payee.
    effective_payee_id = sub.payee_id if sub.payee_id is not None else parent.payee_id
    if existing is None:
        session.add(
            Transaction(
                id=sub.id,
                budget_id=budget_id,
                account_id=parent.account_id,
                category_id=sub.category_id,
                payee_id=effective_payee_id,
                date=parent.date,
                amount_cents=amount_cents,
                memo=sub.memo,
                cleared=parent.cleared,
                approved=parent.approved,
            )
        )
    else:
        existing.budget_id = budget_id
        existing.account_id = parent.account_id
        existing.category_id = sub.category_id
        existing.payee_id = effective_payee_id
        existing.date = parent.date
        existing.amount_cents = amount_cents
        existing.memo = sub.memo
        existing.cleared = parent.cleared
        existing.approved = parent.approved
