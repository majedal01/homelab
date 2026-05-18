"""Question suggestions for the Ask page empty state.

Returns a small mixed list of curated and data-driven prompts. Curated
prompts exercise different tools; data-driven prompts mention the user's
actual top category, recent month, or biggest transaction so the empty
state feels personal.
"""

from __future__ import annotations

from datetime import date as _date
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services.queries import (
    list_budgets_ordered,
    list_transactions,
    spending_by_category,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]

CURATED: tuple[str, ...] = (
    "What were my top spending categories last month?",
    "What did I spend on groceries this month vs last month?",
    "How much did I save this year so far?",
)


class SuggestionResponse(BaseModel):
    suggestions: list[str]


def _format_month(year: int, month: int) -> str:
    return _date(year, month, 1).strftime("%B")


@router.get("/suggestions", response_model=SuggestionResponse)
async def suggestions(
    session: SessionDep,
    budget_id: Annotated[str | None, Query()] = None,
) -> SuggestionResponse:
    # Resolve which budget to riff off. Caller-supplied wins; else first one.
    if budget_id is None:
        budgets = await list_budgets_ordered(session)
        if not budgets:
            return SuggestionResponse(suggestions=list(CURATED[:3]))
        budget_id = budgets[0].id

    today = _date.today()
    month_start = today.replace(day=1)
    # Previous month bounds: the day before this month's first is the
    # previous month's last day; that day's first-of-month is prev_first.
    prev_last_day = month_start - timedelta(days=1)
    prev_first = prev_last_day.replace(day=1)

    data_driven: list[str] = []

    # Top spending category last month → "Why did I spend so much on X in May?"
    try:
        by_cat = await spending_by_category(session, budget_id, prev_first, prev_last_day)
        # spending_by_category returns most-negative first; filter out the
        # uncategorized row when present.
        top_named = next(
            (c for c in by_cat if c.category_name is not None and c.spent_cents < 0),
            None,
        )
        if top_named is not None:
            month_label = _format_month(prev_first.year, prev_first.month)
            data_driven.append(
                f"Why did I spend so much on {top_named.category_name} in {month_label}?"
            )
    except Exception:  # noqa: BLE001
        pass

    # Biggest recent expense → "What was my biggest expense in the last 30 days?"
    try:
        thirty_ago = today - timedelta(days=30)
        recent = await list_transactions(
            session,
            budget_id=budget_id,
            date_from=thirty_ago,
            date_to=today,
            limit=200,
        )
        biggest = min(
            (t for t in recent if t.amount_cents < 0 and not _is_transfer(t)),
            key=lambda t: t.amount_cents,
            default=None,
        )
        if biggest is not None and biggest.payee is not None:
            data_driven.append(
                f"Tell me about that {biggest.payee.name} transaction "
                f"on {biggest.date.isoformat()}."
            )
    except Exception:  # noqa: BLE001
        pass

    # Always include one income/savings prompt as the third data slot.
    data_driven.append("Was my income higher or lower than last month?")

    out = list(CURATED[:2]) + data_driven[:3]
    return SuggestionResponse(suggestions=out[:5])


def _is_transfer(t: object) -> bool:
    """Inline transfer check that mirrors the SQL filter for cases where we're
    iterating Python-side. Safe on attribute access via getattr to avoid
    type assertions across optional FKs."""
    payee = getattr(t, "payee", None)
    if payee is None:
        return False
    return getattr(payee, "transfer_account_id", None) is not None
