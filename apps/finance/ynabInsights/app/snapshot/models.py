"""Pydantic shapes for one budget's YNAB data, held in memory per session.

Same field set as the SQLAlchemy models we're replacing, no ORM. Sort
order on transactions is fixed at fetch (newest first); aggregations
in `queries.py` rely on the list being immutable for the session's
lifetime.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class Account(BaseModel):
    id: str
    name: str
    type: str
    on_budget: bool
    closed: bool
    balance_cents: int


class Category(BaseModel):
    id: str
    name: str
    category_group_id: str | None = None
    category_group_name: str | None = None
    hidden: bool = False
    goal_type: str | None = None
    goal_target_cents: int | None = None
    goal_target_month: date | None = None
    goal_percentage_complete: int | None = None
    goal_overall_left_cents: int | None = None
    goal_months_to_budget: int | None = None


class Payee(BaseModel):
    id: str
    name: str
    transfer_account_id: str | None = None


class Transaction(BaseModel):
    id: str
    date: date
    amount_cents: int
    account_id: str
    payee_id: str | None = None
    category_id: str | None = None
    memo: str | None = None
    transfer_account_id: str | None = None


class YnabSnapshot(BaseModel):
    """One budget's full data, fetched fresh per session."""

    model_config = ConfigDict(frozen=False)

    budget_id: str
    budget_name: str
    currency_iso: str
    fetched_at: datetime
    accounts: Annotated[list[Account], Field(default_factory=list)]
    categories: Annotated[list[Category], Field(default_factory=list)]
    payees: Annotated[list[Payee], Field(default_factory=list)]
    transactions: Annotated[list[Transaction], Field(default_factory=list)]

    # Lookup helpers. Built lazily, cleared on snapshot refresh.

    def category_by_id(self) -> dict[str, Category]:
        return {c.id: c for c in self.categories}

    def account_by_id(self) -> dict[str, Account]:
        return {a.id: a for a in self.accounts}

    def payee_by_id(self) -> dict[str, Payee]:
        return {p.id: p for p in self.payees}
