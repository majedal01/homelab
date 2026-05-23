"""Aggregated report endpoints.

Routes that return pre-aggregated numbers so the frontend doesn't need to
fetch raw transactions and roll up client-side. Important because the
`/transactions` endpoint caps at 500 rows per call, which truncates the
oldest months when a 12-month window is needed for trend visualizations.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.services.queries import monthly_trend

router = APIRouter(prefix="/reports", tags=["reports"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class MonthlyTrendPoint(BaseModel):
    year: int
    month: int
    spending_cents: int
    income_cents: int


class MonthlyTrendResponse(BaseModel):
    points: list[MonthlyTrendPoint]


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
