from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.models import Category
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
            "next_offset": RECENT_PAGE_SIZE,
        },
    )


@router.get("/categories/{category_id}", response_class=HTMLResponse)
async def category_detail(
    request: Request,
    session: SessionDep,
    category_id: str,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
) -> Response:
    category = await session.get(Category, category_id)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")

    today = date.today()
    end = date_to or today
    start = date_from or _first_of_month(end)

    rows = await list_transactions(
        session, category_id=category_id, date_from=start, date_to=end, limit=500
    )
    transactions = [transaction_to_response(t) for t in rows]
    total_cents = sum(t.amount_cents for t in transactions)
    budgets = await list_budgets_ordered(session)

    return templates.TemplateResponse(
        request,
        "category_detail.html",
        {
            "category": category,
            "transactions": transactions,
            "total_cents": total_cents,
            "txn_count": len(transactions),
            "date_from": start,
            "date_to": end,
            "budgets": budgets,
            "selected_budget_id": category.budget_id,
        },
    )


@router.get("/_partials/transactions", response_class=HTMLResponse)
async def partial_transactions(
    request: Request,
    session: SessionDep,
    budget_id: Annotated[str, Query()],
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = RECENT_PAGE_SIZE,
) -> Response:
    """HTML fragment for HTMX-driven load-more. Returns one page of rows
    plus another load-more button if there are still more."""
    rows = await list_transactions(session, budget_id=budget_id, limit=limit, offset=offset)
    recent = [transaction_to_response(t) for t in rows]
    return templates.TemplateResponse(
        request,
        "partials/transaction_rows.html",
        {
            "recent": recent,
            "selected_budget_id": budget_id,
            "has_more": len(recent) == limit,
            "next_offset": offset + limit,
        },
    )
