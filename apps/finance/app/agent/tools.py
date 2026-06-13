"""Tool functions exposed to the Claude agent loop (v2.5).

Each tool takes the per-request YNAB snapshot and a validated Pydantic
input. Outputs are JSON-serializable dicts. No database; the snapshot is
already in memory.

The TOOL_REGISTRY is iterated by the agent loop to build Anthropic
tool specs and to dispatch calls.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.snapshot.models import YnabSnapshot
from app.snapshot.queries import (
    period_summary,
    spending_by_category,
    transactions_in_range,
)


class NoInput(BaseModel):
    pass


class SpendingByCategoryInput(BaseModel):
    start_date: date = Field(description="Inclusive start date.")
    end_date: date = Field(description="Inclusive end date.")


class TransactionsInput(BaseModel):
    category_id: str | None = Field(default=None, description="Filter to a single category.")
    payee_name_contains: str | None = Field(
        default=None,
        description="Case-insensitive substring match on payee name.",
    )
    date_from: date | None = None
    date_to: date | None = None
    limit: int = Field(default=50, ge=1, le=200)


class MonthlySummaryInput(BaseModel):
    year: int = Field(ge=2000, le=2100)
    month: int = Field(ge=1, le=12)


# Tool implementations.


def _cents_to_dollars(c: int) -> float:
    return round(c / 100, 2)


async def _list_accounts(snap: YnabSnapshot, _: NoInput) -> list[dict[str, Any]]:
    return [
        {
            "id": a.id,
            "name": a.name,
            "type": a.type,
            "on_budget": a.on_budget,
            "closed": a.closed,
            "balance_dollars": _cents_to_dollars(a.balance_cents),
        }
        for a in snap.accounts
    ]


async def _list_categories(snap: YnabSnapshot, _: NoInput) -> list[dict[str, Any]]:
    return [
        {
            "id": c.id,
            "name": c.name,
            "hidden": c.hidden,
            "goal_target_dollars": (
                _cents_to_dollars(c.goal_target_cents) if c.goal_target_cents is not None else None
            ),
            "goal_percentage_complete": c.goal_percentage_complete,
        }
        for c in snap.categories
        if not c.hidden
    ]


async def _spending_by_category(
    snap: YnabSnapshot, args: SpendingByCategoryInput
) -> list[dict[str, Any]]:
    return [
        {
            "category_id": row.category_id,
            "category_name": row.category_name,
            "spent_dollars": _cents_to_dollars(-row.spent_cents),
        }
        for row in spending_by_category(snap, args.start_date, args.end_date)
    ]


async def _transactions(snap: YnabSnapshot, args: TransactionsInput) -> list[dict[str, Any]]:
    df = args.date_from or date(1900, 1, 1)
    dt = args.date_to or date(2100, 1, 1)
    rows = transactions_in_range(snap, df, dt)
    payees = snap.payee_by_id()
    cats = snap.category_by_id()

    filtered: list[dict[str, Any]] = []
    needle = args.payee_name_contains.lower() if args.payee_name_contains else None
    for t in rows:
        if args.category_id and t.category_id != args.category_id:
            continue
        payee_name = payees[t.payee_id].name if t.payee_id and t.payee_id in payees else None
        if needle is not None and (payee_name is None or needle not in payee_name.lower()):
            continue
        filtered.append(
            {
                "id": t.id,
                "date": t.date.isoformat(),
                "amount_dollars": _cents_to_dollars(t.amount_cents),
                "payee_name": payee_name,
                "category_name": (
                    cats[t.category_id].name if t.category_id and t.category_id in cats else None
                ),
                "memo": t.memo,
            }
        )
        if len(filtered) >= args.limit:
            break
    return filtered


async def _monthly_summary(snap: YnabSnapshot, args: MonthlySummaryInput) -> dict[str, Any]:
    from calendar import monthrange

    start = date(args.year, args.month, 1)
    end = date(args.year, args.month, monthrange(args.year, args.month)[1])
    summary = period_summary(snap, start, end)
    return {
        "year": args.year,
        "month": args.month,
        "income_dollars": _cents_to_dollars(summary.income_cents),
        "spending_dollars": _cents_to_dollars(summary.spending_cents),
        "net_dollars": _cents_to_dollars(summary.net_income_cents),
        "transaction_count": summary.transaction_count,
        "top_categories": [
            {
                "category_name": row.category_name,
                "net_dollars": _cents_to_dollars(row.net_cents),
            }
            for row in summary.by_category[:5]
        ],
    }


@dataclass
class Tool:
    name: str
    description: str
    input_model: type[BaseModel]
    function: Callable[[YnabSnapshot, Any], Awaitable[Any]]

    def to_anthropic_spec(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_model.model_json_schema(),
        }


TOOL_REGISTRY: dict[str, Tool] = {
    "list_accounts": Tool(
        name="list_accounts",
        description="List the user's accounts in the active budget (with balances).",
        input_model=NoInput,
        function=_list_accounts,
    ),
    "list_categories": Tool(
        name="list_categories",
        description="List the user's categories in the active budget.",
        input_model=NoInput,
        function=_list_categories,
    ),
    "spending_by_category": Tool(
        name="spending_by_category",
        description="Net spending per category across a date range, on-budget only.",
        input_model=SpendingByCategoryInput,
        function=_spending_by_category,
    ),
    "transactions": Tool(
        name="transactions",
        description="Transactions filtered by category, payee substring, and date range.",
        input_model=TransactionsInput,
        function=_transactions,
    ),
    "monthly_summary": Tool(
        name="monthly_summary",
        description="YNAB-style income vs expense summary for one month.",
        input_model=MonthlySummaryInput,
        function=_monthly_summary,
    ),
}
