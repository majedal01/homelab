"""Tests for the dashboard's ask form: the /_partials/ask endpoint and the
form rendered on the dashboard. Agent loop is mocked at the router level."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest_asyncio
from _pytest.monkeypatch import MonkeyPatch
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import AskResult, ToolCall
from app.models import Budget


@pytest_asyncio.fixture(autouse=True)
async def reset_anthropic_key() -> AsyncIterator[None]:
    """Tests in this module set/clear the cached settings' key. Reset after
    each so other test modules see the default (None)."""
    from app.config import get_settings

    yield
    get_settings().anthropic_api_key = None


async def test_dashboard_renders_ask_form(db_session: AsyncSession, client: AsyncClient) -> None:
    # Form only renders when there is at least one budget (otherwise the empty
    # state template is used).
    db_session.add(
        Budget(
            id="b-1",
            name="Main",
            currency="USD",
            last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
        )
    )
    await db_session.commit()
    response = await client.get("/")
    body = response.text
    assert 'hx-post="/_partials/ask"' in body
    assert 'name="question"' in body
    assert "Thinking..." in body


async def test_partial_ask_returns_503_when_key_missing(client: AsyncClient) -> None:
    from app.config import get_settings

    get_settings().anthropic_api_key = None
    response = await client.post("/_partials/ask", data={"question": "hello"})
    assert response.status_code == 503
    assert "not configured" in response.text


async def test_partial_ask_rejects_empty_question(client: AsyncClient) -> None:
    from app.config import get_settings

    get_settings().anthropic_api_key = "test-key"
    response = await client.post("/_partials/ask", data={"question": ""})
    assert response.status_code == 422


async def test_partial_ask_renders_answer(monkeypatch: MonkeyPatch, client: AsyncClient) -> None:
    from app.config import get_settings

    get_settings().anthropic_api_key = "test-key"

    canned = AskResult(
        question="hi",
        answer="You spent $42 on coffee this month.",
        tool_calls=[
            ToolCall(
                tool="spending_by_category",
                input={"budget_id": "b-1"},
                output=[{"category_name": "Coffee", "spent_dollars": 42.0}],
            )
        ],
        turns_used=2,
        stop_reason="end_turn",
    )

    async def fake_run_agent(**kwargs: Any) -> AskResult:
        return canned

    monkeypatch.setattr("app.routers.dashboard.run_agent", fake_run_agent)

    response = await client.post("/_partials/ask", data={"question": "hi"})
    assert response.status_code == 200
    body = response.text
    assert "$42 on coffee" in body
    assert "spending_by_category" in body
    assert "1 tool call(s) over 2 turn(s)" in body


async def test_partial_ask_renders_error_on_exception(
    monkeypatch: MonkeyPatch, client: AsyncClient
) -> None:
    from app.config import get_settings

    get_settings().anthropic_api_key = "test-key"

    async def boom(**kwargs: Any) -> AskResult:
        raise RuntimeError("upstream blew up")

    monkeypatch.setattr("app.routers.dashboard.run_agent", boom)

    response = await client.post("/_partials/ask", data={"question": "anything"})
    assert response.status_code == 500
    body = response.text
    assert "Ask failed" in body
    assert "upstream blew up" in body
