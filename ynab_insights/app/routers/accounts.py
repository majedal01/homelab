from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Account
from app.schemas import AccountResponse

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(
    session: SessionDep,
    budget_id: Annotated[str | None, Query()] = None,
    include_closed: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[AccountResponse]:
    stmt = select(Account).order_by(Account.name)
    if budget_id is not None:
        stmt = stmt.where(Account.budget_id == budget_id)
    if not include_closed:
        stmt = stmt.where(Account.closed.is_(False))
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [AccountResponse.model_validate(a) for a in result.scalars().all()]
