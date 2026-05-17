"""Sync orchestrator.

Pulls all YNAB entities for every accessible budget and upserts them into the
local database. Upserts use SELECT-then-INSERT-or-UPDATE in Python so the same
code path works against both Postgres (prod) and SQLite (tests).
"""
from __future__ import annotations

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Account, Budget, Category, Payee, Transaction
from app.services.ynab_client import (
    YNABAccount,
    YNABBudget,
    YNABCategory,
    YNABClient,
    YNABPayee,
    YNABTransaction,
    milliunits_to_cents,
)


class SyncResult(BaseModel):
    budgets: int = 0
    accounts: int = 0
    categories: int = 0
    payees: int = 0
    transactions: int = 0


async def run_sync(session: AsyncSession, ynab_token: str) -> SyncResult:
    """Run a full sync of all budgets accessible to the given token."""
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

            for txn in await client.list_transactions(budget.id):
                await _upsert_transaction(session, txn, budget.id)
                result.transactions += 1

    await session.commit()
    return result


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
    existing = await session.get(Category, source.id)
    if existing is None:
        session.add(
            Category(
                id=source.id,
                budget_id=budget_id,
                category_group_id=source.category_group_id,
                name=source.name,
                hidden=source.hidden,
            )
        )
    else:
        existing.budget_id = budget_id
        existing.category_group_id = source.category_group_id
        existing.name = source.name
        existing.hidden = source.hidden


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
