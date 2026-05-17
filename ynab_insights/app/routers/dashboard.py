import logging
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import run_agent
from app.config import Settings, get_settings
from app.db import get_session
from app.models import Category
from app.services.queries import (
    cached_spending_by_category,
    list_budgets_ordered,
    list_open_accounts,
    list_transactions,
    monthly_outflows,
    transaction_to_response,
)
from app.templating import templates

logger = logging.getLogger(__name__)

router = APIRouter()

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

RECENT_PAGE_SIZE = 20


def _first_of_month(today: date) -> date:
    return today.replace(day=1)


@router.get("/", response_class=HTMLResponse)
async def dashboard_home(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    budget_id: Annotated[str | None, Query()] = None,
    date_from: Annotated[date | None, Query()] = None,
    date_to: Annotated[date | None, Query()] = None,
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
    range_end = date_to or today
    range_start = date_from or _first_of_month(range_end)
    # The "month_start" / "today" template names are kept for backward compat
    # with existing template fragments that reference them.
    month_start = range_start

    accounts = await list_open_accounts(session, selected)
    on_budget_accounts = [a for a in accounts if a.on_budget]
    tracking_accounts = [a for a in accounts if not a.on_budget]
    on_budget_total = sum(a.balance_cents for a in on_budget_accounts)
    tracking_total = sum(a.balance_cents for a in tracking_accounts)
    monthly = await cached_spending_by_category(session, selected, range_start, range_end)
    trend = await monthly_outflows(session, selected, months=6)

    # Pre-serialize chart inputs into plain dicts/lists so the templates can
    # `tojson` them safely — CategorySpend is a frozen dataclass and tuple
    # rows are not JSON-serializable on their own.
    trend_chart = [
        {"label": ms.strftime("%Y-%m"), "outflow_dollars": round(abs(cents) / 100, 2)}
        for ms, cents in trend
    ]
    category_chart = [
        {
            "name": row.category_name or "Uncategorized",
            "spent_dollars": round(abs(row.spent_cents) / 100, 2),
        }
        for row in monthly
    ]
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
            "on_budget_accounts": on_budget_accounts,
            "tracking_accounts": tracking_accounts,
            "on_budget_total": on_budget_total,
            "tracking_total": tracking_total,
            "monthly_spend": monthly,
            "range_start": range_start,
            "range_end": range_end,
            "month_start": month_start,
            "today": today,
            "trend_chart": trend_chart,
            "category_chart": category_chart,
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


@router.get("/_partials/category_transactions", response_class=HTMLResponse)
async def partial_category_transactions(
    request: Request,
    session: SessionDep,
    category_id: Annotated[str, Query()],
    date_from: Annotated[date, Query()],
    date_to: Annotated[date, Query()],
) -> Response:
    """HTML fragment for the date-range filter on the category drill-down page."""
    rows = await list_transactions(
        session, category_id=category_id, date_from=date_from, date_to=date_to, limit=500
    )
    transactions = [transaction_to_response(t) for t in rows]
    total_cents = sum(t.amount_cents for t in transactions)
    return templates.TemplateResponse(
        request,
        "partials/category_transactions.html",
        {
            "transactions": transactions,
            "total_cents": total_cents,
            "txn_count": len(transactions),
        },
    )


@router.post("/_partials/ask", response_class=HTMLResponse)
async def partial_ask(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    question: Annotated[str, Form(min_length=1, max_length=1000)],
    budget_id: Annotated[str | None, Form()] = None,
) -> Response:
    """HTML fragment for the dashboard's ask form. Same agent loop as the
    `/ask` JSON endpoint; rendered output for HTMX swap."""
    if settings.anthropic_api_key is None:
        return templates.TemplateResponse(
            request,
            "partials/ask_error.html",
            {"detail": "ANTHROPIC_API_KEY is not configured"},
            status_code=503,
        )
    try:
        result = await run_agent(
            session=session,
            settings=settings,
            question=question,
            budget_id=budget_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("ask failed")
        return templates.TemplateResponse(
            request,
            "partials/ask_error.html",
            {"detail": f"{type(exc).__name__}: {exc}"},
            status_code=500,
        )
    return templates.TemplateResponse(
        request,
        "partials/ask_answer.html",
        {"result": result},
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
