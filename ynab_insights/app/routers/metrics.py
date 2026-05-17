from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import Account, Budget, Category, Payee, Transaction
from app.services.metrics import counters, render_prometheus

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(session: SessionDep) -> str:
    """Prometheus-compatible text exposition. Counters reset on restart;
    gauges are computed live from the database on every scrape."""
    gauges: dict[str, int] = {}
    for table, model in [
        ("budgets", Budget),
        ("accounts", Account),
        ("categories", Category),
        ("payees", Payee),
        ("transactions", Transaction),
    ]:
        count = (await session.execute(select(func.count()).select_from(model))).scalar_one()
        gauges[table] = int(count)

    return render_prometheus(counters, gauges)
