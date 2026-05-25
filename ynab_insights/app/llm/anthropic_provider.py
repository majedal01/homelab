"""Anthropic concrete provider.

Owns the full tool-use loop. Caller supplies a tool dispatcher; the
provider calls it when a `tool_use` block finishes streaming, then
pushes the result back into the conversation and continues the loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

import anthropic

from app.llm.base import (
    DoneEvent,
    EnhancedCopyResult,
    InvalidApiKeyError,
    LlmProvider,
    ProviderBillingError,
    ProviderUnavailableError,
    StreamEvent,
    TokenEvent,
    ToolResultEvent,
    ToolSpec,
    ToolUseEvent,
)

logger = logging.getLogger(__name__)

ToolDispatcher = Callable[[str, dict[str, Any]], Awaitable[tuple[Any, bool]]]


class AnthropicProvider(LlmProvider):
    name = "anthropic"

    async def ping(self) -> None:
        client = anthropic.AsyncAnthropic(api_key=self._api_key.get_secret_value())
        try:
            await client.messages.create(
                model=self._model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ok"}],
            )
        except anthropic.AuthenticationError as e:
            raise InvalidApiKeyError() from e
        except anthropic.PermissionDeniedError as e:
            raise ProviderBillingError() from e
        except anthropic.APIError as e:
            logger.info("anthropic ping failed: %s", type(e).__name__)
            raise ProviderUnavailableError() from e

    async def enhance_copy(
        self,
        *,
        system_prompt: str,
        user_message: str,
        timeout_seconds: float,
    ) -> EnhancedCopyResult:
        client = anthropic.AsyncAnthropic(api_key=self._api_key.get_secret_value())
        try:
            response = await asyncio.wait_for(
                client.messages.create(
                    model=self._model,
                    max_tokens=512,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}],
                ),
                timeout=timeout_seconds,
            )
            text_block = next(
                (b for b in response.content if isinstance(b, anthropic.types.TextBlock)),
                None,
            )
            if text_block is None:
                raise ValueError("no text block in response")
            parsed = json.loads(text_block.text)
            return EnhancedCopyResult(
                title=str(parsed["title"]).strip(),
                summary=str(parsed["summary"]).strip(),
                used_llm=True,
            )
        except (
            TimeoutError,
            anthropic.APIError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            logger.info("anthropic enhance failed: %s", type(exc).__name__)
            return EnhancedCopyResult(title="", summary="", used_llm=False)

    async def stream_agent(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        tool_dispatcher: ToolDispatcher,
        max_tool_calls: int,
        max_duration_seconds: int,
    ) -> AsyncIterator[StreamEvent]:
        client = anthropic.AsyncAnthropic(api_key=self._api_key.get_secret_value())
        tool_specs = [_to_anthropic_tool(t) for t in tools]
        start = time.monotonic()
        tool_call_count = 0
        msgs = list(messages)

        for turn in range(max_tool_calls + 1):
            if time.monotonic() - start > max_duration_seconds:
                yield DoneEvent(turns_used=turn, stop_reason="timeout")
                return

            tool_use_buffers: dict[int, dict[str, Any]] = {}
            pending: list[dict[str, Any]] = []

            async with client.messages.stream(
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                tools=tool_specs,  # type: ignore[arg-type]
                messages=msgs,  # type: ignore[arg-type]
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
                            yield TokenEvent(text=delta.text)
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
                            yield ToolUseEvent(
                                id=buf["id"],
                                tool=buf["name"],
                                input=cast(dict[str, Any], input_data),
                            )
                            pending.append(
                                {"id": buf["id"], "name": buf["name"], "input": input_data}
                            )
                final = await stream.get_final_message()

            if final.stop_reason == "end_turn":
                yield DoneEvent(turns_used=turn + 1, stop_reason="end_turn")
                return
            if final.stop_reason != "tool_use":
                yield DoneEvent(
                    turns_used=turn + 1, stop_reason=str(final.stop_reason or "unknown")
                )
                return

            msgs.append({"role": "assistant", "content": final.content})

            tool_results: list[dict[str, Any]] = []
            for p in pending:
                tool_call_count += 1
                if tool_call_count > max_tool_calls:
                    yield DoneEvent(turns_used=turn + 1, stop_reason="max_tool_calls")
                    return
                output, is_error = await tool_dispatcher(p["name"], p["input"])
                yield ToolResultEvent(id=p["id"], output=output, is_error=is_error)
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": p["id"],
                        "content": output if is_error else json.dumps(output, default=str),
                        **({"is_error": True} if is_error else {}),
                    }
                )
            msgs.append({"role": "user", "content": tool_results})

        yield DoneEvent(turns_used=max_tool_calls, stop_reason="max_tool_calls")


def _to_anthropic_tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "name": spec.name,
        "description": spec.description,
        "input_schema": spec.parameters_schema,
    }
