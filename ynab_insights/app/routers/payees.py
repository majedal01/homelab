from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Payee
from app.schemas import PayeeResponse

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/payees", response_model=list[PayeeResponse])
async def list_payees(
    session: SessionDep,
    budget_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PayeeResponse]:
    stmt = select(Payee).order_by(Payee.name)
    if budget_id is not None:
        stmt = stmt.where(Payee.budget_id == budget_id)
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [PayeeResponse.model_validate(p) for p in result.scalars().all()]
