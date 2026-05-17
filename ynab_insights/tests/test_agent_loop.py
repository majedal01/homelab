"""Tests for the Claude agent loop with the Anthropic SDK mocked.

We synthesize Anthropic response objects to drive specific paths through the
loop without ever calling the real API.
"""

from datetime import UTC, datetime
from typing import Any, Literal
from unittest.mock import AsyncMock

import pytest_asyncio
from _pytest.monkeypatch import MonkeyPatch
from anthropic.types import (
    Message,
    TextBlock,
    ToolUseBlock,
    Usage,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import run_agent
from app.config import Settings, get_settings
from app.models import Budget

StopReason = Literal["end_turn", "max_tokens", "stop_sequence", "tool_use", "pause_turn", "refusal"]


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
    await db_session.commit()
    return db_session


def _msg(content: list[Any], stop_reason: StopReason) -> Message:
    return Message(
        id="msg-test",
        type="message",
        role="assistant",
        content=content,
        model="claude-test",
        stop_reason=stop_reason,
        stop_sequence=None,
        usage=Usage(input_tokens=0, output_tokens=0),
    )


def _text_msg(text: str) -> Message:
    return _msg([TextBlock(type="text", text=text)], stop_reason="end_turn")


def _tool_use_msg(tool_name: str, tool_input: dict[str, Any], use_id: str = "tu-1") -> Message:
    return _msg(
        [ToolUseBlock(type="tool_use", id=use_id, name=tool_name, input=tool_input)],
        stop_reason="tool_use",
    )


def _settings_with_key() -> Settings:
    s = get_settings()
    s.anthropic_api_key = "test-key"
    s.ask_max_turns = 5
    return s


def _patch_anthropic(monkeypatch: MonkeyPatch, responses: list[Message]) -> AsyncMock:
    """Patch anthropic.AsyncAnthropic so its messages.create yields the
    given responses in order."""
    create = AsyncMock(side_effect=responses)
    client = AsyncMock()
    client.messages.create = create

    def fake_constructor(*args: Any, **kwargs: Any) -> AsyncMock:
        return client

    monkeypatch.setattr("app.agent.loop.anthropic.AsyncAnthropic", fake_constructor)
    return create


async def test_run_agent_returns_text_when_end_turn(
    monkeypatch: MonkeyPatch, seeded: AsyncSession
) -> None:
    _patch_anthropic(monkeypatch, [_text_msg("Hello, world.")])

    result = await run_agent(
        session=seeded,
        settings=_settings_with_key(),
        question="Hi",
    )
    assert result.answer == "Hello, world."
    assert result.turns_used == 1
    assert result.stop_reason == "end_turn"
    assert result.tool_calls == []


async def test_run_agent_executes_tool_then_returns_answer(
    monkeypatch: MonkeyPatch, seeded: AsyncSession
) -> None:
    """Two-turn flow: Claude requests list_budgets, we execute, then Claude
    summarizes."""
    _patch_anthropic(
        monkeypatch,
        [
            _tool_use_msg("list_budgets", {}),
            _text_msg("You have one budget: Main."),
        ],
    )

    result = await run_agent(
        session=seeded,
        settings=_settings_with_key(),
        question="What budgets do I have?",
    )
    assert result.turns_used == 2
    assert result.stop_reason == "end_turn"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool == "list_budgets"
    # The tool actually ran against the seeded DB
    assert any(b["name"] == "Main" for b in result.tool_calls[0].output)


async def test_run_agent_handles_unknown_tool_gracefully(
    monkeypatch: MonkeyPatch, seeded: AsyncSession
) -> None:
    _patch_anthropic(
        monkeypatch,
        [
            _tool_use_msg("does_not_exist", {"foo": "bar"}),
            _text_msg("Sorry, I cannot answer that."),
        ],
    )

    result = await run_agent(
        session=seeded,
        settings=_settings_with_key(),
        question="???",
    )
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].is_error
    assert "unknown tool" in result.tool_calls[0].output


async def test_run_agent_handles_invalid_tool_input(
    monkeypatch: MonkeyPatch, seeded: AsyncSession
) -> None:
    """spending_by_category requires budget_id, start_date, end_date. Missing
    fields should surface as an error tool_result instead of crashing."""
    _patch_anthropic(
        monkeypatch,
        [
            _tool_use_msg("spending_by_category", {"budget_id": "b-1"}),
            _text_msg("(after seeing the error)"),
        ],
    )

    result = await run_agent(
        session=seeded,
        settings=_settings_with_key(),
        question="What did I spend?",
    )
    assert result.tool_calls[0].is_error
    assert result.stop_reason == "end_turn"


async def test_run_agent_max_turns_cap(monkeypatch: MonkeyPatch, seeded: AsyncSession) -> None:
    """If Claude keeps calling tools past the budget, return max_turns."""
    # 5 tool_use responses, never end_turn
    tool_msgs = [_tool_use_msg("list_budgets", {}, use_id=f"tu-{i}") for i in range(10)]
    _patch_anthropic(monkeypatch, tool_msgs)

    settings = _settings_with_key()
    settings.ask_max_turns = 3
    result = await run_agent(
        session=seeded,
        settings=settings,
        question="Loop forever",
    )
    assert result.stop_reason == "max_turns"
    assert result.turns_used == 3
    assert len(result.tool_calls) == 3
