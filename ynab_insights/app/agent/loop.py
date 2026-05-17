"""Claude tool-use agent loop.

Sends a user question to Claude with tool definitions, dispatches any tool
calls Claude makes against the local DB, loops until Claude returns a final
text answer or the turn budget is exhausted.
"""

from __future__ import annotations

import json
import logging
from typing import Any, cast

import anthropic
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import TOOL_REGISTRY
from app.config import Settings

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


def _build_system_prompt(today_iso: str, default_budget_id: str | None) -> str:
    budget_hint = (
        f"The user's default budget id is `{default_budget_id}`. "
        "Pass this as `budget_id` to tools unless the user clearly means a different budget."
        if default_budget_id
        else "The user has not specified a default budget. Use list_budgets to discover one if needed."
    )
    return (
        "You are an analyst answering questions about the user's personal YNAB budget data.\n\n"
        "You have read-only tools that query a local Postgres database synced from YNAB.\n\n"
        "Conventions:\n"
        f"- Today is {today_iso}.\n"
        "- Negative amounts are outflows (spending). Positive are inflows.\n"
        "- Tool responses use `dollars` fields (already converted from YNAB milliunits).\n"
        f"- {budget_hint}\n\n"
        "Use the tools to look up actual numbers; do not make them up. After you have what "
        "you need, give a concise answer with the specific figures and a brief one-line "
        "explanation. Format dollar amounts as $1,234.56."
    )


def _extract_text(response: anthropic.types.Message) -> str:
    parts = [block.text for block in response.content if block.type == "text"]
    return "\n".join(p for p in parts if p)


async def run_agent(
    *,
    session: AsyncSession,
    settings: Settings,
    question: str,
    budget_id: str | None = None,
) -> AskResult:
    if settings.anthropic_api_key is None:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    tool_specs = [t.to_anthropic_spec() for t in TOOL_REGISTRY.values()]

    from datetime import date as _date

    system = _build_system_prompt(
        today_iso=_date.today().isoformat(),
        default_budget_id=budget_id or settings.ynab_budget_id,
    )

    messages: list[dict[str, Any]] = [{"role": "user", "content": question}]
    trace: list[ToolCall] = []

    for turn in range(settings.ask_max_turns):
        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            system=system,
            tools=tool_specs,
            messages=messages,
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
            logger.warning("unexpected stop reason: %s", response.stop_reason)
            return AskResult(
                question=question,
                answer=_extract_text(response) or "(no text returned)",
                tool_calls=trace,
                turns_used=turn + 1,
                stop_reason=str(response.stop_reason or "unknown"),
            )

        # Echo the assistant turn back in history so Claude has full context next loop.
        messages.append({"role": "assistant", "content": response.content})

        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            tool_input = cast(dict[str, Any], block.input)
            tool = TOOL_REGISTRY.get(block.name)
            if tool is None:
                err = f"unknown tool: {block.name}"
                trace.append(
                    ToolCall(tool=block.name, input=tool_input, output=err, is_error=True)
                )
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
                output = await tool.function(session, validated)
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
                trace.append(
                    ToolCall(tool=block.name, input=tool_input, output=err, is_error=True)
                )
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
        turns_used=settings.ask_max_turns,
        stop_reason="max_turns",
    )
