"""Streaming variant of the Claude tool-use agent loop (v2.5).

Yields Server-Sent Events as the model generates tokens, calls tools, and
finishes the turn. Caller passes the session snapshot and Anthropic key.

Cancellation contract unchanged: if the consumer abandons the generator
the cancellation propagates into the Anthropic stream context which
closes the upstream connection.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from datetime import date as _date
from typing import Any, cast

import anthropic
from pydantic import SecretStr

from app.agent.loop import _build_system_prompt
from app.agent.tools import TOOL_REGISTRY
from app.config import Settings
from app.snapshot.models import YnabSnapshot

logger = logging.getLogger(__name__)


def _sse(event: str, data: Any) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


async def _run_tool(
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


async def stream_agent(
    *,
    snapshot: YnabSnapshot,
    anthropic_key: SecretStr,
    settings: Settings,
    question: str,
    history: list[dict[str, Any]],
) -> AsyncIterator[str]:
    """Yield SSE-formatted strings for the agent turn. Enforces guardrails."""
    if len(question) > settings.agent_input_max_chars:
        yield _sse(
            "error",
            {"message": f"Question is over the {settings.agent_input_max_chars}-character limit."},
        )
        return

    client = anthropic.AsyncAnthropic(api_key=anthropic_key.get_secret_value())
    tool_specs = [t.to_anthropic_spec() for t in TOOL_REGISTRY.values()]
    system = _build_system_prompt(_date.today().isoformat(), snapshot)
    messages: list[dict[str, Any]] = list(history) + [{"role": "user", "content": question}]

    start = time.monotonic()
    tool_call_count = 0

    try:
        for turn in range(settings.agent_max_tool_calls + 1):
            if time.monotonic() - start > settings.agent_max_duration_seconds:
                yield _sse(
                    "done",
                    {"turns_used": turn, "stop_reason": "timeout"},
                )
                return

            pending_tools: list[dict[str, Any]] = []
            tool_use_buffers: dict[int, dict[str, Any]] = {}

            async with client.messages.stream(
                model=settings.anthropic_model,
                max_tokens=4096,
                system=system,
                tools=tool_specs,  # type: ignore[arg-type]
                messages=messages,  # type: ignore[arg-type]
            ) as stream:
                async for raw_event in stream:
                    event: Any = raw_event
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

                final = await stream.get_final_message()

            if final.stop_reason == "end_turn":
                yield _sse(
                    "done",
                    {"turns_used": turn + 1, "stop_reason": "end_turn"},
                )
                return

            if final.stop_reason != "tool_use":
                yield _sse(
                    "done",
                    {
                        "turns_used": turn + 1,
                        "stop_reason": str(final.stop_reason or "unknown"),
                    },
                )
                return

            messages.append({"role": "assistant", "content": final.content})

            tool_result_blocks: list[dict[str, Any]] = []
            for pending in pending_tools:
                tool_call_count += 1
                if tool_call_count > settings.agent_max_tool_calls:
                    yield _sse(
                        "done",
                        {"turns_used": turn + 1, "stop_reason": "max_tool_calls"},
                    )
                    return
                tool_input = cast(dict[str, Any], pending["input"])
                output, is_error = await _run_tool(snapshot, pending["name"], tool_input)
                yield _sse(
                    "tool_result",
                    {"id": pending["id"], "output": output, "is_error": is_error},
                )
                tool_result_blocks.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": pending["id"],
                        "content": (output if is_error else json.dumps(output, default=str)),
                        **({"is_error": True} if is_error else {}),
                    }
                )

            messages.append({"role": "user", "content": tool_result_blocks})

        yield _sse(
            "done",
            {"turns_used": settings.agent_max_tool_calls, "stop_reason": "max_tool_calls"},
        )
    except asyncio.CancelledError:
        logger.info("ask stream cancelled by client")
        raise
    except anthropic.APIError as exc:
        logger.exception("anthropic API error mid-stream")
        yield _sse("error", {"message": f"Anthropic API error: {exc}"})
    except Exception as exc:  # noqa: BLE001
        logger.exception("agent stream failed")
        yield _sse("error", {"message": f"{type(exc).__name__}: {exc}"})
