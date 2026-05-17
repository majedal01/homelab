from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.services.queries import (
    list_budgets_ordered,
    list_open_accounts,
    list_transactions,
    spending_by_category,
    transaction_to_response,
)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

_templates_dir = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(_templates_dir))

RECENT_PAGE_SIZE = 20


def _first_of_month(today: date) -> date:
    return today.replace(day=1)


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    budget_id: Annotated[str | None, Query()] = None,
) -> Response:
    budgets = await list_budgets_ordered(session)
    if not budgets:
        return templates.TemplateResponse(
            request,
            "dashboard_empty.html",
            {"budgets": [], "selected_budget_id": None},
        )

    selected = budget_id or settings.ynab_budget_id or budgets[0].id

    today = date.today()
    month_start = _first_of_month(today)

    accounts = await list_open_accounts(session, selected)
    monthly = await spending_by_category(session, selected, month_start, today)
    recent_models = await list_transactions(
        session, budget_id=selected, limit=RECENT_PAGE_SIZE, offset=0
    )
    recent = [transaction_to_response(t) for t in recent_models]

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "budgets": budgets,
            "selected_budget_id": selected,
            "accounts": accounts,
            "monthly_spend": monthly,
            "month_start": month_start,
            "today": today,
            "recent": recent,
            "has_more": len(recent) == RECENT_PAGE_SIZE,
        },
    )
