"""Insights Feed API.

Five endpoints under `/api/insights`:

- `GET    /api/insights`               feed listing (paginated, dismissable)
- `GET    /api/insights/{id}`          single insight detail
- `POST   /api/insights/{id}/dismiss`  mark dismissed (idempotent)
- `POST   /api/insights/generate`      on-demand run of one or all generators
- `GET    /api/insights/runs`          generator-run observability listing
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db import get_session
from app.insights import all_generators, execute_generator, get_generator
from app.insights.schemas import (
    CardType,
    GenerateResponse,
    InsightResponse,
    InsightRunResponse,
)
from app.models import Insight, InsightRun
from app.services.queries import list_budgets_ordered

router = APIRouter(prefix="/api/insights", tags=["insights"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def _utc(dt: datetime | None) -> datetime | None:
    """Normalize naive datetimes to UTC. SQLite (used in tests) drops the
    timezone on round-trip even for `DateTime(timezone=True)` columns, so
    a freshly-set tz-aware value and a re-read value would otherwise
    serialize differently. Postgres preserves tz natively; this is a no-op
    there."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def _to_response(row: Insight) -> InsightResponse:
    return InsightResponse(
        id=row.id,
        budget_id=row.budget_id,
        card_type=cast(CardType, row.card_type),
        dedup_key=row.dedup_key,
        title=row.title,
        summary=row.summary,
        structured_data=row.structured_data,  # type: ignore[arg-type]
        generated_at=_utc(row.generated_at),  # type: ignore[arg-type]
        refreshed_at=_utc(row.refreshed_at),  # type: ignore[arg-type]
        dismissed_at=_utc(row.dismissed_at),
        llm_enhanced=row.llm_enhanced,
    )


async def _resolve_budget_id(
    session: AsyncSession, settings: Settings, supplied: str | None
) -> str | None:
    if supplied is not None:
        return supplied
    if settings.ynab_budget_id is not None:
        return settings.ynab_budget_id
    budgets = await list_budgets_ordered(session)
    return budgets[0].id if budgets else None


@router.get("", response_model=list[InsightResponse])
async def list_insights(
    session: SessionDep,
    settings: SettingsDep,
    budget_id: Annotated[str | None, Query()] = None,
    include_dismissed: Annotated[bool, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InsightResponse]:
    resolved = await _resolve_budget_id(session, settings, budget_id)
    if resolved is None:
        return []
    stmt = select(Insight).where(Insight.budget_id == resolved)
    if not include_dismissed:
        stmt = stmt.where(Insight.dismissed_at.is_(None))
    stmt = stmt.order_by(Insight.refreshed_at.desc(), Insight.id.desc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).scalars().all()
    return [_to_response(r) for r in rows]


@router.get("/runs", response_model=list[InsightRunResponse])
async def list_runs(
    session: SessionDep,
    card_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[InsightRunResponse]:
    stmt = select(InsightRun).order_by(InsightRun.started_at.desc())
    if card_type is not None:
        stmt = stmt.where(InsightRun.card_type == card_type)
    rows = (await session.execute(stmt.limit(limit))).scalars().all()
    return [
        InsightRunResponse(
            id=r.id,
            card_type=r.card_type,
            started_at=_utc(r.started_at),  # type: ignore[arg-type]
            finished_at=_utc(r.finished_at),
            status=r.status,
            duration_ms=r.duration_ms,
            insights_created=r.insights_created,
            insights_updated=r.insights_updated,
            error=r.error,
        )
        for r in rows
    ]


@router.get("/{insight_id}", response_model=InsightResponse)
async def get_insight(insight_id: int, session: SessionDep) -> InsightResponse:
    row = await session.get(Insight, insight_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    return _to_response(row)


@router.post("/{insight_id}/dismiss", response_model=InsightResponse)
async def dismiss_insight(insight_id: int, session: SessionDep) -> InsightResponse:
    row = await session.get(Insight, insight_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    if row.dismissed_at is None:
        row.dismissed_at = datetime.now(UTC)
        await session.commit()
    return _to_response(row)


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    session: SessionDep,
    settings: SettingsDep,
    card_type: Annotated[str | None, Query()] = None,
    budget_id: Annotated[str | None, Query()] = None,
) -> GenerateResponse:
    resolved = await _resolve_budget_id(session, settings, budget_id)
    if resolved is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="no budget available; run a sync first",
        )

    if card_type is not None:
        cls = get_generator(card_type)
        if cls is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"unknown card_type: {card_type}",
            )
        targets = [cls]
    else:
        targets = all_generators()

    run_ids: list[int] = []
    for gen_cls in targets:
        outcome = await execute_generator(gen_cls, session, settings, resolved)
        run_ids.append(outcome.run_id)
    return GenerateResponse(run_ids=run_ids)
