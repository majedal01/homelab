"""Streaming variant of the Claude tool-use agent loop.

Yields Server-Sent Events as the model generates tokens, calls tools, and
finishes the turn. Used by `POST /ask` to give the frontend an
incremental view of the answer and the tool trace.

Cancellation contract: if the consumer abandons the generator (e.g. the
HTTP client disconnects), `asyncio.CancelledError` propagates into the
`async with client.messages.stream(...)` context, which closes the
upstream Anthropic connection. We don't burn tokens we won't display.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from datetime import date as _date
from typing import Any, cast

import anthropic
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.loop import _build_system_prompt
from app.agent.tools import TOOL_REGISTRY
from app.config import Settings
from app.services.metrics import counters

logger = logging.getLogger(__name__)


def _sse(event: str, data: Any) -> str:
    """Format one Server-Sent Event. `data` is JSON-encoded unless already a str."""
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    # Single-line `data:` is required for parsing on the client; we don't emit
    # multi-line bodies. JSON dumps escape newlines for us.
    return f"event: {event}\ndata: {payload}\n\n"


async def _run_tool(
    session: AsyncSession,
    tool_name: str,
    tool_input: dict[str, Any],
) -> tuple[Any, bool]:
    """Run one tool. Returns (output, is_error)."""
    tool = TOOL_REGISTRY.get(tool_name)
    if tool is None:
        return f"unknown tool: {tool_name}", True
    try:
        validated = tool.input_model.model_validate(tool_input)
        output = await tool.function(session, validated)
        return output, False
    except Exception as exc:  # noqa: BLE001
        logger.exception("tool %s failed", tool_name)
        counters.tool_errors += 1
        return f"{type(exc).__name__}: {exc}", True


async def stream_agent(
    *,
    session: AsyncSession,
    settings: Settings,
    question: str,
    budget_id: str | None,
    history: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """Yield SSE-formatted strings for the agent turn.

    `history` is the prior conversation in Anthropic message format
    (`[{"role": "user"|"assistant", "content": ...}, ...]`). The frontend
    posts it on every request; backend stays stateless.
    """
    if settings.anthropic_api_key is None:
        yield _sse("error", {"message": "ANTHROPIC_API_KEY is not configured"})
        return

    counters.ask_calls += 1
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    tool_specs = [t.to_anthropic_spec() for t in TOOL_REGISTRY.values()]

    system = _build_system_prompt(
        today_iso=_date.today().isoformat(),
        default_budget_id=budget_id or settings.ynab_budget_id,
    )

    messages: list[dict[str, Any]] = list(history) + [
        {"role": "user", "content": question}
    ]

    try:
        for turn in range(settings.ask_max_turns):
            # Per-turn collectors. Tool-use blocks complete their JSON input
            # incrementally; we emit the `tool_use` SSE event at content_block_stop
            # once the input is fully assembled.
            pending_tools: list[dict[str, Any]] = []
            tool_use_buffers: dict[int, dict[str, Any]] = {}

            async with client.messages.stream(
                model=settings.anthropic_model,
                max_tokens=4096,
                system=system,
                tools=tool_specs,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            ) as stream:
                async for event in stream:
                    et = event.type
                    if et == "content_block_start":
                        block = event.content_block
                        if block.type == "tool_use":
                            tool_use_buffers[event.index] = {
                                "id": block.id,
                                "name": block.name,
                                "input_json": "",
                            }
                    elif et == "content_block_delta":
                        delta = event.delta
                        dtype = getattr(delta, "type", None)
                        if dtype == "text_delta":
                            yield _sse("token", delta.text)
                        elif dtype == "input_json_delta":
                            buf = tool_use_buffers.get(event.index)
                            if buf is not None:
                                buf["input_json"] += delta.partial_json
                    elif et == "content_block_stop":
                        buf = tool_use_buffers.pop(event.index, None)
                        if buf is not None:
                            try:
                                input_data = json.loads(buf["input_json"] or "{}")
                            except json.JSONDecodeError:
                                input_data = {}
                            yield _sse(
                                "tool_use",
                                {
                                    "id": buf["id"],
                                    "tool": buf["name"],
                                    "input": input_data,
                                },
                            )
                            pending_tools.append(
                                {
                                    "id": buf["id"],
                                    "name": buf["name"],
                                    "input": input_data,
                                }
                            )
                    # message_start/delta/stop don't carry payload we forward.

                final = await stream.get_final_message()

            if final.stop_reason == "end_turn":
                yield _sse(
                    "done",
                    {"turns_used": turn + 1, "stop_reason": "end_turn"},
                )
                return

            if final.stop_reason != "tool_use":
                logger.warning("unexpected stop reason: %s", final.stop_reason)
                yield _sse(
                    "done",
                    {
                        "turns_used": turn + 1,
                        "stop_reason": str(final.stop_reason or "unknown"),
                    },
                )
                return

            # Append the assistant message verbatim so the next turn has full
            # context, including the tool_use blocks Claude just emitted.
            messages.append({"role": "assistant", "content": final.content})

            # Dispatch each tool, emit results.
            tool_result_blocks: list[dict[str, Any]] = []
            for pending in pending_tools:
                tool_input = cast(dict[str, Any], pending["input"])
                output, is_error = await _run_tool(
                    session, pending["name"], tool_input
                )
                yield _sse(
                    "tool_result",
                    {
                        "id": pending["id"],
                        "output": output,
                        "is_error": is_error,
                    },
                )
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": pending["id"],
                        "content": (
                            output
                            if is_error
                            else json.dumps(output, default=str)
                        ),
                        **({"is_error": True} if is_error else {}),
                    }
                )

            messages.append({"role": "user", "content": tool_result_blocks})

        yield _sse(
            "done",
            {"turns_used": settings.ask_max_turns, "stop_reason": "max_turns"},
        )
    except asyncio.CancelledError:
        # Client closed the connection mid-stream. The `async with` block's
        # __aexit__ has already shut the Anthropic stream down. Just log and
        # re-raise so the runtime tears the generator down cleanly.
        logger.info("ask stream cancelled by client")
        raise
    except anthropic.APIError as exc:
        counters.ask_failures += 1
        logger.exception("anthropic API error mid-stream")
        yield _sse("error", {"message": f"Anthropic API error: {exc}"})
    except Exception as exc:  # noqa: BLE001
        counters.ask_failures += 1
        logger.exception("agent stream failed")
        yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})
