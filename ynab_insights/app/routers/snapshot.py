"""Read endpoints over the in-memory YnabSnapshot.

Backs the `/explore` page. Thin views; the aggregation logic lives in
`app/snapshot/queries.py`. Every endpoint requires an authenticated
session and operates on `session.snapshot`; no database, no upstream
YNAB calls.
"""

from __future__ import annotations

from calendar import monthrange
from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.session.middleware import CurrentSessionDep
from app.snapshot.queries import (
    monthly_trend,
    net_worth_cents,
    period_summary,
    spending_by_category,
)

router = APIRouter(prefix="/api/snapshot", tags=["snapshot"])


# --- response shapes --------------------------------------------------------


class AccountResponse(BaseModel):
    id: str
    name: str
    type: str
    on_budget: bool
    closed: bool
    balance_cents: int


class CategoryResponse(BaseModel):
    id: str
    name: str
    hidden: bool
    goal_type: str | None
    goal_target_cents: int | None
    goal_overall_left_cents: int | None
    goal_percentage_complete: int | None
    # This-month net spending (positive = outflow). Convenience for the UI so
    # the page doesn't have to fan out per-category aggregation queries.
    this_month_spend_cents: int


class TransactionResponse(BaseModel):
    id: str
    date: date
    amount_cents: int
    account_id: str
    account_name: str | None
    category_id: str | None
    category_name: str | None
    payee_id: str | None
    payee_name: str | None
    memo: str | None


class CategoryNetResponse(BaseModel):
    category_id: str | None
    category_name: str | None
    net_cents: int


class PeriodSummaryResponse(BaseModel):
    date_from: date
    date_to: date
    income_cents: int
    spending_cents: int
    net_income_cents: int
    transaction_count: int
    by_category: list[CategoryNetResponse]


class MonthlyTrendPointResponse(BaseModel):
    year: int
    month: int
    income_cents: int
    spending_cents: int


class MonthlyTrendResponse(BaseModel):
    points: list[MonthlyTrendPointResponse]


class OverviewKPIs(BaseModel):
    """Snapshot of headline numbers for the Overview tab. Income, spending,
    and savings rate are scoped to the current calendar month."""

    net_worth_cents: int
    this_month_income_cents: int
    this_month_spending_cents: int
    this_month_net_cents: int
    savings_rate: float | None
    transaction_count: int  # total across the entire snapshot


# --- helpers ----------------------------------------------------------------


def _month_bounds(today: date) -> tuple[date, date]:
    return date(today.year, today.month, 1), date(
        today.year, today.month, monthrange(today.year, today.month)[1]
    )


# --- endpoints --------------------------------------------------------------


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(session: CurrentSessionDep) -> list[AccountResponse]:
    snap = session.snapshot
    if snap is None:
        raise HTTPException(409, detail={"error": "no_budget_selected"})
    return [
        AccountResponse(
            id=a.id,
            name=a.name,
            type=a.type,
            on_budget=a.on_budget,
            closed=a.closed,
            balance_cents=a.balance_cents,
        )
        for a in snap.accounts
    ]


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(session: CurrentSessionDep) -> list[CategoryResponse]:
    snap = session.snapshot
    if snap is None:
        raise HTTPException(409, detail={"error": "no_budget_selected"})
    start, end = _month_bounds(date.today())
    this_month = {
        row.category_id: -row.spent_cents for row in spending_by_category(snap, start, end)
    }
    return [
        CategoryResponse(
            id=c.id,
            name=c.name,
            hidden=c.hidden,
            goal_type=c.goal_type,
            goal_target_cents=c.goal_target_cents,
            goal_overall_left_cents=c.goal_overall_left_cents,
            goal_percentage_complete=c.goal_percentage_complete,
            this_month_spend_cents=this_month.get(c.id, 0),
        )
        for c in snap.categories
        if not c.hidden
    ]


@router.get("/transactions", response_model=list[TransactionResponse])
async def list_transactions(
    session: CurrentSessionDep,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    category_id: Annotated[str | None, Query()] = None,
    account_id: Annotated[str | None, Query()] = None,
    payee_contains: Annotated[str | None, Query(min_length=1, max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TransactionResponse]:
    """Paginated transactions slice. Filters compose; payee_contains is a
    case-insensitive substring match."""
    snap = session.snapshot
    if snap is None:
        raise HTTPException(409, detail={"error": "no_budget_selected"})

    payees = snap.payee_by_id()
    accounts = snap.account_by_id()
    categories = snap.category_by_id()
    needle = payee_contains.lower() if payee_contains else None
    lower_bound = date_from or date(1900, 1, 1)
    upper_bound = date_to or date(2100, 1, 1)

    out: list[TransactionResponse] = []
    matched = 0
    for t in snap.transactions:  # already newest-first
        if not (lower_bound <= t.date <= upper_bound):
            continue
        if category_id is not None and t.category_id != category_id:
            continue
        if account_id is not None and t.account_id != account_id:
            continue
        payee = payees.get(t.payee_id) if t.payee_id else None
        if needle is not None and (payee is None or needle not in payee.name.lower()):
            continue
        if matched < offset:
            matched += 1
            continue
        out.append(
            TransactionResponse(
                id=t.id,
                date=t.date,
                amount_cents=t.amount_cents,
                account_id=t.account_id,
                account_name=accounts[t.account_id].name if t.account_id in accounts else None,
                category_id=t.category_id,
                category_name=(
                    categories[t.category_id].name
                    if t.category_id and t.category_id in categories
                    else None
                ),
                payee_id=t.payee_id,
                payee_name=payee.name if payee else None,
                memo=t.memo,
            )
        )
        if len(out) >= limit:
            break
    return out


@router.get("/summary", response_model=PeriodSummaryResponse)
async def summary(
    session: CurrentSessionDep,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> PeriodSummaryResponse:
    """YNAB-style Income vs Expense rollup for [date_from, date_to].
    Defaults to the current calendar month."""
    snap = session.snapshot
    if snap is None:
        raise HTTPException(409, detail={"error": "no_budget_selected"})

    start, end = _month_bounds(date.today())
    if date_from is not None:
        start = date_from
    if date_to is not None:
        end = date_to

    p = period_summary(snap, start, end)
    return PeriodSummaryResponse(
        date_from=p.date_from,
        date_to=p.date_to,
        income_cents=p.income_cents,
        spending_cents=p.spending_cents,
        net_income_cents=p.net_income_cents,
        transaction_count=p.transaction_count,
        by_category=[
            CategoryNetResponse(
                category_id=r.category_id,
                category_name=r.category_name,
                net_cents=r.net_cents,
            )
            for r in p.by_category
        ],
    )


@router.get("/monthly-trend", response_model=MonthlyTrendResponse)
async def monthly_trend_endpoint(
    session: CurrentSessionDep,
    months: Annotated[int, Query(ge=1, le=36)] = 12,
) -> MonthlyTrendResponse:
    snap = session.snapshot
    if snap is None:
        raise HTTPException(409, detail={"error": "no_budget_selected"})
    rows = monthly_trend(snap, months)
    return MonthlyTrendResponse(
        points=[
            MonthlyTrendPointResponse(
                year=r.year,
                month=r.month,
                income_cents=r.income_cents,
                spending_cents=r.spending_cents,
            )
            for r in rows
        ]
    )


@router.get("/overview", response_model=OverviewKPIs)
async def overview(session: CurrentSessionDep) -> OverviewKPIs:
    """Headline KPIs for the Overview tab. Single round-trip so the page
    doesn't fan out into N parallel calls."""
    snap = session.snapshot
    if snap is None:
        raise HTTPException(409, detail={"error": "no_budget_selected"})

    nw = net_worth_cents(snap)
    start, end = _month_bounds(date.today())
    p = period_summary(snap, start, end)
    rate = (p.income_cents - p.spending_cents) / p.income_cents if p.income_cents > 0 else None
    return OverviewKPIs(
        net_worth_cents=nw,
        this_month_income_cents=p.income_cents,
        this_month_spending_cents=p.spending_cents,
        this_month_net_cents=p.net_income_cents,
        savings_rate=round(rate, 3) if rate is not None else None,
        transaction_count=len(snap.transactions),
    )
