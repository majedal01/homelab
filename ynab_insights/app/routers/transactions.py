from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas import TransactionResponse
from app.services.queries import list_transactions, transaction_to_response

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/transactions", response_model=list[TransactionResponse])
async def get_transactions(
    session: SessionDep,
    budget_id: Annotated[str | None, Query()] = None,
    account_id: Annotated[str | None, Query()] = None,
    category_id: Annotated[str | None, Query()] = None,
    payee_id: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TransactionResponse]:
    transactions = await list_transactions(
        session,
        budget_id=budget_id,
        account_id=account_id,
        category_id=category_id,
        payee_id=payee_id,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
        offset=offset,
    )
    return [transaction_to_response(t) for t in transactions]
