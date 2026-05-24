"""Claude tool-use agent loop (v2.5, non-streaming).

Keeps the unit-testable surface for tool dispatch + max-turns capping
that the streaming variant in `stream.py` mirrors. Caller passes the
session's snapshot and Anthropic key explicitly; the loop never reads
from settings for tokens.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, cast

import anthropic
from pydantic import BaseModel, SecretStr

from app.agent.tools import TOOL_REGISTRY
from app.config import Settings
from app.snapshot.models import YnabSnapshot

logger = logging.getLogger(__name__)


class ToolCall(BaseModel):
    tool: str
    input: dict[str, Any]
    output: Any
    is_error: bool = False


class AskResult(BaseModel):
    question: str
    answer: str
    tool_calls: list[ToolCall]
    turns_used: int
    stop_reason: str


def _build_system_prompt(today_iso: str, snapshot: YnabSnapshot) -> str:
    return (
        "You are an analyst answering questions about the user's personal "
        "YNAB budget data.\n\n"
        f"Active budget: {snapshot.budget_name}, currency {snapshot.currency_iso}.\n"
        f"Today is {today_iso}. Snapshot fetched at {snapshot.fetched_at.isoformat()}.\n\n"
        "Conventions:\n"
        "- Negative amounts are outflows (spending). Positive are inflows.\n"
        "- Tool outputs use `_dollars` fields (already converted from cents).\n"
        "- Tools operate only on the active budget; budget_id is implicit.\n\n"
        "Use the tools to look up actual numbers. Do not invent figures. "
        "After you have what you need, answer concisely with the figures and "
        "a brief explanation. Format dollar amounts as $1,234.56."
    )


def _extract_text(response: anthropic.types.Message) -> str:
    parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(p for p in parts if p)


async def run_agent(
    *,
    snapshot: YnabSnapshot,
    anthropic_key: SecretStr,
    settings: Settings,
    question: str,
) -> AskResult:
    """One non-streaming Ask turn. Enforces the agent guardrails."""
    if len(question) > settings.agent_input_max_chars:
        raise ValueError(f"question too long ({len(question)} > {settings.agent_input_max_chars})")

    client = anthropic.AsyncAnthropic(api_key=anthropic_key.get_secret_value())
    tool_specs = [t.to_anthropic_spec() for t in TOOL_REGISTRY.values()]

    from datetime import date as _date

    system = _build_system_prompt(_date.today().isoformat(), snapshot)
    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    trace: list[ToolCall] = []

    try:
        result = await asyncio.wait_for(
            _loop(client, settings, snapshot, system, messages, tool_specs, trace, question),
            timeout=settings.agent_max_duration_seconds,
        )
    except TimeoutError:
        return AskResult(
            question=question,
            answer="(agent exceeded duration cap)",
            tool_calls=trace,
            turns_used=len(trace),
            stop_reason="timeout",
        )
    return result


async def _loop(  # noqa: PLR0913 (params are all required context)
    client: anthropic.AsyncAnthropic,
    settings: Settings,
    snapshot: YnabSnapshot,
    system: str,
    messages: list[dict[str, Any]],
    tool_specs: list[dict[str, Any]],
    trace: list[ToolCall],
    question: str,
) -> AskResult:
    tool_call_count = 0
    for turn in range(settings.agent_max_tool_calls + 1):
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            system=system,
            tools=tool_specs,  # type: ignore[arg-type]
            messages=messages,  # type: ignore[arg-type]
        )

        if response.stop_reason == "end_turn":
            return AskResult(
                question=question,
                answer=_extract_text(response) or "(no text returned)",
                tool_calls=trace,
                turns_used=turn + 1,
                stop_reason="end_turn",
            )

        if response.stop_reason != "tool_use":
            return AskResult(
                question=question,
                answer=_extract_text(response) or "(no text returned)",
                tool_calls=trace,
                turns_used=turn + 1,
                stop_reason=str(response.stop_reason or "unknown"),
            )

        messages.append({"role": "assistant", "content": response.content})

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_input = cast(dict[str, Any], block.input)
            tool = TOOL_REGISTRY.get(block.name)
            tool_call_count += 1
            if tool_call_count > settings.agent_max_tool_calls:
                return AskResult(
                    question=question,
                    answer="(agent exceeded tool-call cap)",
                    tool_calls=trace,
                    turns_used=turn + 1,
                    stop_reason="max_tool_calls",
                )
            if tool is None:
                err = f"unknown tool: {block.name}"
                trace.append(ToolCall(tool=block.name, input=tool_input, output=err, is_error=True))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": err,
                        "is_error": True,
                    }
                )
                continue
            try:
                validated = tool.input_model.model_validate(tool_input)
                output = await tool.function(snapshot, validated)
                trace.append(ToolCall(tool=block.name, input=tool_input, output=output))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(output, default=str),
                    }
                )
            except Exception as exc:  # noqa: BLE001
                err = f"{type(exc).__name__}: {exc}"
                logger.exception("tool %s failed", block.name)
                trace.append(ToolCall(tool=block.name, input=tool_input, output=err, is_error=True))
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": err,
                        "is_error": True,
                    }
                )

        messages.append({"role": "user", "content": tool_results})

    return AskResult(
        question=question,
        answer="(reached max turns without final answer)",
        tool_calls=trace,
        turns_used=settings.agent_max_tool_calls,
        stop_reason="max_tool_calls",
    )
