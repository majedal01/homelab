"""Streaming Ask agent.

Resolves the user's provider (Anthropic or OpenAI), delegates the full
tool-use loop to the provider, and re-emits the provider's normalized
`StreamEvent`s as Server-Sent Events on the wire. The v2.5 SSE event
shape is preserved (`token`, `tool_use`, `tool_result`, `done`, `error`)
so the frontend doesn't need to care which provider is in play.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import date as _date
from typing import Any

from pydantic import SecretStr

from app.agent.tools import TOOL_REGISTRY
from app.config import Settings
from app.llm import (
    DEFAULT_MODEL_FOR_PROVIDER,
    DoneEvent,
    ErrorEvent,
    Provider,
    StreamEvent,
    TokenEvent,
    ToolResultEvent,
    ToolSpec,
    ToolUseEvent,
    build_provider,
    detect_provider,
)
from app.snapshot.models import YnabSnapshot

logger = logging.getLogger(__name__)


def _sse(event_name: str, data: Any) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event_name}\ndata: {payload}\n\n"


def _system_prompt(snapshot: YnabSnapshot) -> str:
    return (
        "You are an analyst answering questions about the user's personal "
        "YNAB budget data.\n\n"
        f"Active budget: {snapshot.budget_name}, currency {snapshot.currency_iso}.\n"
        f"Today is {_date.today().isoformat()}. "
        f"Snapshot fetched at {snapshot.fetched_at.isoformat()}.\n\n"
        "Conventions:\n"
        "- Negative amounts are outflows (spending). Positive are inflows.\n"
        "- Tool outputs use `_dollars` fields (already converted from cents).\n"
        "- Tools operate only on the active budget; budget_id is implicit.\n\n"
        "Use the tools to look up actual numbers. Do not invent figures. "
        "After you have what you need, answer concisely with the figures and "
        "a brief explanation. Format dollar amounts as $1,234.56."
    )


def _tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name=t.name,
            description=t.description,
            parameters_schema=t.input_model.model_json_schema(),
        )
        for t in TOOL_REGISTRY.values()
    ]


async def _dispatch_tool(
    snapshot: YnabSnapshot,
    tool_name: str,
    tool_input: dict[str, Any],
) -> tuple[Any, bool]:
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        return f"unknown tool: {tool_name}", True
    try:
        validated = tool.input_model.model_validate(tool_input)
        output = await tool.function(snapshot, validated)
        return output, False
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool %s failed", tool_name)
        return f"{type(exc).__name__}: {exc}", True


def _event_to_sse(event: StreamEvent) -> str:
    if isinstance(event, TokenEvent):
        return _sse("token", event.text)
    if isinstance(event, ToolUseEvent):
        return _sse("tool_use", {"id": event.id, "tool": event.tool, "input": event.input})
    if isinstance(event, ToolResultEvent):
        return _sse(
            "tool_result",
            {"id": event.id, "output": event.output, "is_error": event.is_error},
        )
    if isinstance(event, DoneEvent):
        return _sse("done", {"turns_used": event.turns_used, "stop_reason": event.stop_reason})
    if isinstance(event, ErrorEvent):
        return _sse("error", {"message": event.message})
    return _sse("error", {"message": "unknown event"})


async def stream_agent(
    *,
    snapshot: YnabSnapshot,
    anthropic_key: SecretStr,
    settings: Settings,
    question: str,
    history: list[dict[str, Any]],
    anthropic_model: str | None = None,
    provider: Provider | None = None,
) -> AsyncIterator[str]:
    """Yield SSE-formatted strings for the agent turn. Enforces guardrails.

    `anthropic_key` is a misnomer in v2.6d — it may be an OpenAI key too;
    the parameter name is preserved so existing call sites don't churn.
    `provider` is detected from the key prefix when not supplied.
    """
    if len(question) > settings.agent_input_max_chars:
        yield _sse(
            "error",
            {"message": f"Question is over the {settings.agent_input_max_chars}-character limit."},
        )
        return

    inferred = provider or detect_provider(anthropic_key.get_secret_value())
    if inferred is None:
        yield _sse("error", {"message": "Key didn't match a known provider."})
        return
    model = anthropic_model or settings.anthropic_model or DEFAULT_MODEL_FOR_PROVIDER[inferred]

    llm = build_provider(inferred, anthropic_key, model)
    messages = list(history) + [{"role": "user", "content": question}]

    # Wrap the in-memory snapshot into a closure for the tool dispatcher so
    # the provider can call tools without knowing the snapshot shape.
    async def dispatcher(name: str, args: dict[str, Any]) -> tuple[Any, bool]:
        return await _dispatch_tool(snapshot, name, args)

    start = time.monotonic()
    try:
        async for event in llm.stream_agent(
            system_prompt=_system_prompt(snapshot),
            messages=messages,
            tools=_tool_specs(),
            tool_dispatcher=dispatcher,
            max_tool_calls=settings.agent_max_tool_calls,
            max_duration_seconds=settings.agent_max_duration_seconds,
        ):
            yield _event_to_sse(event)
            # Defense in depth against a misbehaving provider that doesn't
            # honor max_duration: cap at the wrapper level too.
            if time.monotonic() - start > settings.agent_max_duration_seconds + 5:
                yield _sse("done", {"turns_used": 0, "stop_reason": "timeout"})
                return
    except asyncio.CancelledError:
        logger.info("ask stream cancelled by client")
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent stream failed")
        yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})
