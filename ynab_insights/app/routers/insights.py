"""Insights API (v2.5).

Operates on `request.state.session.snapshot`. No database. Dismissals are
client-side (localStorage); the server returns every generated insight.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, cast

from fastapi import APIRouter, HTTPException, Query, status

from app.insights import all_generators, get_generator, run_all_generators
from app.insights.base import Insight
from app.insights.schemas import (
    CardType,
    GenerateResponse,
    InsightResponse,
    InsightRunResponse,
)
from app.session.middleware import CurrentSessionDep

router = APIRouter(prefix="/api/insights", tags=["insights"])


def _to_response(row: Insight) -> InsightResponse:
    return InsightResponse(
        id=row.id,
        budget_id=row.budget_id,
        card_type=cast(CardType, row.card_type),
        dedup_key=row.dedup_key,
        title=row.title,
        summary=row.summary,
        structured_data=row.structured_data,  # type: ignore[arg-type]
        generated_at=row.generated_at,
        refreshed_at=row.refreshed_at,
        dismissed_at=row.dismissed_at,
        llm_enhanced=row.llm_enhanced,
    )


@router.get("", response_model=list[InsightResponse])
async def list_insights(
    session: CurrentSessionDep,
    card_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[InsightResponse]:
    insights = cast(list[Insight], session.insights)
    if card_type is not None:
        insights = [i for i in insights if i.card_type == card_type]
    insights = sorted(insights, key=lambda i: i.refreshed_at, reverse=True)
    return [_to_response(i) for i in insights[offset : offset + limit]]


@router.get("/runs", response_model=list[InsightRunResponse])
async def list_runs(
    session: CurrentSessionDep,
    card_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[InsightRunResponse]:
    runs = list(session.runs)
    if card_type is not None:
        runs = [r for r in runs if r.card_type == card_type]
    runs = sorted(runs, key=lambda r: r.started_at, reverse=True)[:limit]
    return [
        InsightRunResponse(
            id=r.id,
            card_type=r.card_type,
            started_at=r.started_at,
            finished_at=r.finished_at,
            status=r.status,
            duration_ms=r.duration_ms,
            insights_created=r.insights_created,
            insights_updated=r.insights_updated,
            error=r.error,
        )
        for r in runs
    ]


@router.get("/{insight_id}", response_model=InsightResponse)
async def get_insight(insight_id: int, session: CurrentSessionDep) -> InsightResponse:
    for i in cast(list[Insight], session.insights):
        if i.id == insight_id:
            return _to_response(i)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")


@router.post("/generate", response_model=GenerateResponse)
async def generate(
    session: CurrentSessionDep,
    card_type: Annotated[str | None, Query()] = None,
) -> GenerateResponse:
    """Run one generator or all of them against the session's snapshot."""
    if session.is_demo:
        # Demo insights are baked-in and immutable. Re-running the generators
        # would either no-op (no LLM key) or trip the rate limiter.
        return GenerateResponse(run_ids=[])
    if session.snapshot is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"error": "no_budget_selected", "message": "Pick a budget first."},
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

    insights_list = cast(list[Insight], session.insights)
    runs_list = list(session.runs)
    by_key: dict[tuple[str, str], Insight] = {(i.budget_id, i.dedup_key): i for i in insights_list}

    next_id = max((i.id for i in insights_list), default=0) + 1
    next_run_id = max((r.id for r in runs_list), default=0) + 1

    merged, records, run_ids = await run_all_generators(
        generators=targets,
        snapshot=session.snapshot,
        anthropic_key=session.anthropic_key,
        anthropic_model=session.anthropic_model,
        existing=by_key,
        next_id=next_id,
        next_run_id=next_run_id,
    )

    session.insights = merged
    session.runs = runs_list + records
    session.last_active_at = datetime.now(UTC)

    return GenerateResponse(run_ids=run_ids)
