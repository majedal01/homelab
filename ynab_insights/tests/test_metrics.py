"""Tests for the /metrics endpoint and the render helper."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Budget
from app.services.metrics import Counters, counters, render_prometheus


@pytest_asyncio.fixture(autouse=True)
async def reset_counters() -> AsyncIterator[None]:
    counters.sync_runs = 0
    counters.sync_failures = 0
    counters.ask_calls = 0
    counters.ask_failures = 0
    counters.tool_errors = 0
    yield


def test_render_includes_counters_and_gauges() -> None:
    c = Counters(sync_runs=3, ask_calls=5, tool_errors=1)
    output = render_prometheus(c, {"budgets": 2, "transactions": 9999})
    assert "ynab_insights_sync_runs_total 3" in output
    assert "ynab_insights_ask_calls_total 5" in output
    assert "ynab_insights_tool_errors_total 1" in output
    assert "ynab_insights_budgets_rows 2" in output
    assert "ynab_insights_transactions_rows 9999" in output


def test_render_includes_help_and_type_lines() -> None:
    output = render_prometheus(Counters(), {})
    # Prometheus exposition format requires HELP and TYPE for each metric
    assert "# HELP ynab_insights_sync_runs_total" in output
    assert "# TYPE ynab_insights_sync_runs_total counter" in output


async def test_metrics_endpoint_returns_text_with_real_gauges(
    db_session: AsyncSession, client: AsyncClient
) -> None:
    db_session.add(
        Budget(
            id="b-1",
            name="Main",
            currency="USD",
            last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    await db_session.commit()
    response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    # Gauge for budgets reflects seeded data
    assert "ynab_insights_budgets_rows 1" in body
    # Other counters present at zero
    assert "ynab_insights_sync_runs_total 0" in body
