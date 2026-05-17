"""Typed tool functions exposed to the Claude agent loop.

Each tool has:
- A Pydantic input model (so Claude gets a JSON schema and we get validation)
- An async function that takes (session, validated_input) and returns
  JSON-serializable output

The TOOL_REGISTRY is iterated by the agent loop to build Anthropic tool specs
and to dispatch tool calls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.queries import (
    list_accounts_for_budget,
    list_budgets_ordered,
    list_categories_for_budget,
    list_transactions,
    monthly_summary,
    spending_by_category,
    transaction_to_response,
)

# Input schemas. Keep these minimal; Claude will populate them.


class ListBudgetsInput(BaseModel):
    pass


class ListAccountsInput(BaseModel):
    budget_id: str | None = Field(
        default=None, description="If omitted, returns accounts across all budgets."
    )


class ListCategoriesInput(BaseModel):
    budget_id: str | None = Field(
        default=None, description="If omitted, returns categories across all budgets."
    )


class SpendingByCategoryInput(BaseModel):
    budget_id: str = Field(description="The budget to aggregate within.")
    start_date: date = Field(description="Inclusive start date.")
    end_date: date = Field(description="Inclusive end date.")


class TransactionsInput(BaseModel):
    budget_id: str
    category_id: str | None = Field(default=None, description="Filter to a single category.")
    payee_name_contains: str | None = Field(
        default=None,
        description="Case-insensitive substring match on payee name (e.g. 'starbucks').",
    )
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=50, ge=1, le=200)


class MonthlySummaryInput(BaseModel):
    budget_id: str
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


# Tool implementations.


async def _list_budgets(session: AsyncSession, _: ListBudgetsInput) -> list[dict[str, Any]]:
    rows = await list_budgets_ordered(session)
    return [{"id": r.id, "name": r.name, "currency": r.currency} for r in rows]


async def _list_accounts(session: AsyncSession, inp: ListAccountsInput) -> list[dict[str, Any]]:
    rows = await list_accounts_for_budget(session, inp.budget_id)
    return [
        {
            "id": r.id,
            "budget_id": r.budget_id,
            "name": r.name,
            "type": r.type,
            "balance_dollars": round(r.balance_cents / 100, 2),
            "on_budget": r.on_budget,
        }
        for r in rows
    ]


async def _list_categories(session: AsyncSession, inp: ListCategoriesInput) -> list[dict[str, Any]]:
    rows = await list_categories_for_budget(session, inp.budget_id)
    return [
        {"id": r.id, "budget_id": r.budget_id, "name": r.name, "hidden": r.hidden} for r in rows
    ]


async def _spending_by_category(
    session: AsyncSession, inp: SpendingByCategoryInput
) -> list[dict[str, Any]]:
    rows = await spending_by_category(session, inp.budget_id, inp.start_date, inp.end_date)
    return [
        {
            "category_id": r.category_id,
            "category_name": r.category_name or "Uncategorized",
            "spent_dollars": round(-r.spent_cents / 100, 2),  # positive = amount spent
        }
        for r in rows
    ]


async def _transactions(session: AsyncSession, inp: TransactionsInput) -> list[dict[str, Any]]:
    rows = await list_transactions(
        session,
        budget_id=inp.budget_id,
        category_id=inp.category_id,
        payee_name_contains=inp.payee_name_contains,
        date_from=inp.date_from,
        date_to=inp.date_to,
        limit=inp.limit,
    )
    return [
        {
            "id": t.id,
            "date": t.date.isoformat(),
            "amount_dollars": round(t.amount_cents / 100, 2),
            "account_name": t.account_name,
            "category_name": t.category_name,
            "payee_name": t.payee_name,
            "memo": t.memo,
        }
        for t in (transaction_to_response(r) for r in rows)
    ]


async def _monthly_summary(session: AsyncSession, inp: MonthlySummaryInput) -> dict[str, Any]:
    summary = await monthly_summary(session, inp.budget_id, inp.year, inp.month)
    return {
        "year": summary.year,
        "month": summary.month,
        "total_inflow_dollars": round(summary.total_inflow_cents / 100, 2),
        "total_outflow_dollars": round(summary.total_outflow_cents / 100, 2),
        "transaction_count": summary.transaction_count,
        "top_categories": [
            {
                "category_name": c.category_name or "Uncategorized",
                "spent_dollars": round(-c.spent_cents / 100, 2),
            }
            for c in summary.top_categories
        ],
    }


# Registry.


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    function: Callable[[AsyncSession, Any], Awaitable[Any]]

    def to_anthropic_spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }


TOOL_REGISTRY: dict[str, Tool] = {
    "list_budgets": Tool(
        name="list_budgets",
        description=(
            "Return all YNAB budgets the user has access to. Use this to discover budget IDs."
        ),
        input_model=ListBudgetsInput,
        function=_list_budgets,
    ),
    "list_accounts": Tool(
        name="list_accounts",
        description=(
            "List non-closed accounts with their current balance. Optionally filter by budget_id."
        ),
        input_model=ListAccountsInput,
        function=_list_accounts,
    ),
    "list_categories": Tool(
        name="list_categories",
        description="List categories. Use to find a category_id for a follow-up query.",
        input_model=ListCategoriesInput,
        function=_list_categories,
    ),
    "spending_by_category": Tool(
        name="spending_by_category",
        description=(
            "Total outflows (spending) grouped by category for a date range. "
            "Returns categories ordered by amount spent (largest first)."
        ),
        input_model=SpendingByCategoryInput,
        function=_spending_by_category,
    ),
    "transactions": Tool(
        name="transactions",
        description=(
            "Search transactions with optional filters. Use payee_name_contains for "
            "natural-language payee lookups like 'starbucks' or 'amazon'."
        ),
        input_model=TransactionsInput,
        function=_transactions,
    ),
    "monthly_summary": Tool(
        name="monthly_summary",
        description=(
            "Get inflow, outflow, transaction count, and top 5 spending categories "
            "for a specific month."
        ),
        input_model=MonthlySummaryInput,
        function=_monthly_summary,
    ),
}
