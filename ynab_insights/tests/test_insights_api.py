"""End-to-end tests for the /api/insights HTTP surface."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Budget, Insight, InsightRun


@pytest_asyncio.fixture
async def seeded(db_session: AsyncSession) -> AsyncSession:
    db_session.add(
        Budget(
            id="b-1",
            name="Main",
            currency="USD",
            last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    db_session.add(
        Budget(
            id="b-2",
            name="Other",
            currency="USD",
            last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    now = datetime.now(UTC)
    db_session.add_all(
        [
            Insight(
                id=1,
                budget_id="b-1",
                card_type="cashflow_forecast",
                dedup_key="forecast:b-1:2026-W21",
                title="Forecast",
                summary="ok",
                structured_data={
                    "card_type": "cashflow_forecast",
                    "starting_balance_cents": 100000,
                    "daily_net_cents": 0,
                    "projected_30d_cents": 100000,
                    "projected_60d_cents": 100000,
                    "projected_90d_cents": 100000,
                    "lookback_days": 90,
                    "top_spending_categories": [],
                },
                generated_at=now - timedelta(days=2),
                refreshed_at=now - timedelta(days=2),
                llm_enhanced=False,
            ),
            Insight(
                id=2,
                budget_id="b-1",
                card_type="subscription_audit",
                dedup_key="subscription:p:1599:monthly",
                title="Netflix",
                summary="Netflix sub",
                structured_data={
                    "card_type": "subscription_audit",
                    "payee_id": "p",
                    "payee_name": "Netflix",
                    "cadence": "monthly",
                    "amount_cents": 1599,
                    "monthly_cost_cents": 1599,
                    "annual_cost_cents": 19188,
                    "occurrences": [],
                    "first_seen": date(2026, 2, 1).isoformat(),
                    "last_seen": date(2026, 4, 1).isoformat(),
                },
                generated_at=now,
                refreshed_at=now,
                llm_enhanced=False,
            ),
            Insight(
                id=3,
                budget_id="b-1",
                card_type="spending_anomaly",
                dedup_key="anomaly:c:2026-W20",
                title="Anomaly",
                summary="spike",
                structured_data={
                    "card_type": "spending_anomaly",
                    "category_id": "c",
                    "category_name": "Groceries",
                    "week_start": date(2026, 5, 16).isoformat(),
                    "week_end": date(2026, 5, 22).isoformat(),
                    "current_week_spend_cents": 40000,
                    "baseline_mean_cents": 5000,
                    "baseline_stdev_cents": 600,
                    "z_score": 5.0,
                    "deviation_ratio": 7.0,
                    "top_transactions": [],
                },
                generated_at=now - timedelta(days=10),
                refreshed_at=now - timedelta(days=10),
                dismissed_at=now - timedelta(days=9),
                llm_enhanced=False,
            ),
            Insight(
                id=4,
                budget_id="b-2",
                card_type="subscription_audit",
                dedup_key="subscription:p2:999:monthly",
                title="Spotify",
                summary="other-budget sub",
                structured_data={
                    "card_type": "subscription_audit",
                    "payee_id": "p2",
                    "payee_name": "Spotify",
                    "cadence": "monthly",
                    "amount_cents": 999,
                    "monthly_cost_cents": 999,
                    "annual_cost_cents": 11988,
                    "occurrences": [],
                    "first_seen": date(2026, 2, 1).isoformat(),
                    "last_seen": date(2026, 4, 1).isoformat(),
                },
                generated_at=now,
                refreshed_at=now,
                llm_enhanced=False,
            ),
        ]
    )
    db_session.add_all(
        [
            InsightRun(
                id=10,
                card_type="subscription_audit",
                started_at=now - timedelta(hours=1),
                finished_at=now - timedelta(hours=1, minutes=-1),
                status="ok",
                duration_ms=120,
                insights_created=1,
                insights_updated=0,
            ),
            InsightRun(
                id=11,
                card_type="cashflow_forecast",
                started_at=now - timedelta(minutes=10),
                finished_at=now - timedelta(minutes=10, seconds=-30),
                status="error",
                duration_ms=30,
                insights_created=0,
                insights_updated=0,
                error="RuntimeError: boom",
            ),
        ]
    )
    await db_session.commit()
    return db_session


async def test_list_excludes_dismissed_by_default(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/api/insights", params={"budget_id": "b-1"})
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()]
    assert ids == [2, 1]  # newest first, dismissed (#3) excluded


async def test_list_includes_dismissed_when_asked(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get(
        "/api/insights",
        params={"budget_id": "b-1", "include_dismissed": "true"},
    )
    assert response.status_code == 200
    ids = {r["id"] for r in response.json()}
    assert ids == {1, 2, 3}


async def test_list_filters_by_budget(seeded: AsyncSession, client: AsyncClient) -> None:
    response = await client.get("/api/insights", params={"budget_id": "b-2"})
    assert response.status_code == 200
    rows = response.json()
    assert len(rows) == 1
    assert rows[0]["id"] == 4


async def test_get_insight_returns_payload(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/api/insights/2")
    assert response.status_code == 200
    payload = response.json()
    assert payload["card_type"] == "subscription_audit"
    assert payload["structured_data"]["payee_name"] == "Netflix"


async def test_get_insight_404(seeded: AsyncSession, client: AsyncClient) -> None:
    response = await client.get("/api/insights/999")
    assert response.status_code == 404


async def test_dismiss_sets_dismissed_at_and_is_idempotent(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    first = await client.post("/api/insights/1/dismiss")
    assert first.status_code == 200
    assert first.json()["dismissed_at"] is not None

    second = await client.post("/api/insights/1/dismiss")
    assert second.status_code == 200
    assert second.json()["dismissed_at"] == first.json()["dismissed_at"]


async def test_runs_endpoint_lists_most_recent_first(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get("/api/insights/runs")
    assert response.status_code == 200
    rows = response.json()
    assert [r["id"] for r in rows] == [11, 10]
    assert rows[0]["status"] == "error"
    assert rows[1]["status"] == "ok"


async def test_runs_filter_by_card_type(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.get(
        "/api/insights/runs", params={"card_type": "subscription_audit"}
    )
    assert response.status_code == 200
    rows = response.json()
    assert [r["id"] for r in rows] == [10]


async def test_generate_runs_all_when_no_card_type(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.post(
        "/api/insights/generate", params={"budget_id": "b-1"}
    )
    assert response.status_code == 200
    payload = response.json()
    # Four registered generators → four run rows produced.
    assert len(payload["run_ids"]) == 4


async def test_generate_rejects_unknown_card_type(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.post(
        "/api/insights/generate",
        params={"budget_id": "b-1", "card_type": "not_a_real_card"},
    )
    assert response.status_code == 404


async def test_generate_with_explicit_card_type_runs_only_that(
    seeded: AsyncSession, client: AsyncClient
) -> None:
    response = await client.post(
        "/api/insights/generate",
        params={"budget_id": "b-1", "card_type": "cashflow_forecast"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["run_ids"]) == 1
