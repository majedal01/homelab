from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Category
from app.schemas import CategoryResponse

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/categories", response_model=list[CategoryResponse])
async def list_categories(
    session: SessionDep,
    budget_id: Annotated[str | None, Query()] = None,
    include_hidden: Annotated[bool, Query()] = True,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CategoryResponse]:
    stmt = select(Category).order_by(Category.name)
    if budget_id is not None:
        stmt = stmt.where(Category.budget_id == budget_id)
    if not include_hidden:
        stmt = stmt.where(Category.hidden.is_(False))
    stmt = stmt.limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [CategoryResponse.model_validate(c) for c in result.scalars().all()]
