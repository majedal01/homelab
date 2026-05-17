from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Budget
from app.schemas import BudgetResponse

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/budgets", response_model=list[BudgetResponse])
async def list_budgets(
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[BudgetResponse]:
    stmt = select(Budget).order_by(Budget.name).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [BudgetResponse.model_validate(b) for b in result.scalars().all()]
