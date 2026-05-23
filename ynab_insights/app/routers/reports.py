"""Aggregated report endpoints.

Routes that return pre-aggregated numbers so the frontend doesn't need to
fetch raw transactions and roll up client-side. Important because the
`/transactions` endpoint caps at 500 rows per call, which truncates the
oldest months when a wide window is needed for trend or KPI rollups.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services.queries import monthly_trend, period_summary

router = APIRouter(prefix="/reports", tags=["reports"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class MonthlyTrendPoint(BaseModel):
    year: int
    month: int
    spending_cents: int
    income_cents: int


class MonthlyTrendResponse(BaseModel):
    points: list[MonthlyTrendPoint]


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


@router.get("/monthly-spending", response_model=MonthlyTrendResponse)
async def monthly_spending(
    session: SessionDep,
    budget_id: Annotated[str, Query(min_length=1)],
    months: Annotated[int, Query(ge=1, le=36)] = 12,
) -> MonthlyTrendResponse:
    rows = await monthly_trend(session, budget_id, months)
    return MonthlyTrendResponse(
        points=[
            MonthlyTrendPoint(
                year=r.year,
                month=r.month,
                spending_cents=r.spending_cents,
                income_cents=r.income_cents,
            )
            for r in rows
        ]
    )


@router.get("/period-summary", response_model=PeriodSummaryResponse)
async def period_summary_endpoint(
    session: SessionDep,
    budget_id: Annotated[str, Query(min_length=1)],
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
) -> PeriodSummaryResponse:
    """YNAB-style Income vs. Expense rollup for an arbitrary date range.

    The dashboard calls this twice (current period + previous period of
    equal length) to drive the KPI tiles and the donut from one source,
    keeping the donut total identical to "This month spending" by
    construction.
    """
    summary = await period_summary(session, budget_id, date_from, date_to)
    return PeriodSummaryResponse(
        date_from=summary.date_from,
        date_to=summary.date_to,
        income_cents=summary.income_cents,
        spending_cents=summary.spending_cents,
        net_income_cents=summary.net_income_cents,
        transaction_count=summary.transaction_count,
        by_category=[
            CategoryNetResponse(
                category_id=row.category_id,
                category_name=row.category_name,
                net_cents=row.net_cents,
            )
            for row in summary.by_category
        ],
    )
