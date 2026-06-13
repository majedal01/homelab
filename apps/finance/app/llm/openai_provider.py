"""OpenAI concrete provider.

Owns the full tool-use loop, mirrors AnthropicProvider's contract but
against the OpenAI chat.completions API.

OpenAI differences vs Anthropic that the abstraction hides:
- Tool spec lives under `{type:"function", function:{name, description, parameters}}`.
- Tool calls arrive as `choices[0].delta.tool_calls[i].function.arguments`
  delta strings, indexed by position. We assemble them per index.
- Tool results go back as `{role: "tool", tool_call_id: ..., content: ...}`
  messages, NOT as user-role content blocks.
- The system prompt is just a `{role: "system"}` message at the head.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import AsyncIterator
from typing import Any

import openai
from openai import AsyncOpenAI
from pydantic import SecretStr

from app.llm.base import (
    DoneEvent,
    EnhancedCopyResult,
    InvalidApiKeyError,
    LlmProvider,
    ProviderBillingError,
    ProviderUnavailableError,
    StreamEvent,
    TokenEvent,
    ToolDispatcher,
    ToolResultEvent,
    ToolSpec,
    ToolUseEvent,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(LlmProvider):
    name = "openai"

    def __init__(self, api_key: SecretStr, model: str) -> None:
        super().__init__(api_key, model)

    async def ping(self) -> None:
        client = AsyncOpenAI(api_key=self._api_key.get_secret_value())
        try:
            await client.chat.completions.create(
                model=self._model,
                max_tokens=1,
                messages=[{"role": "user", "content": "ok"}],
            )
        except openai.AuthenticationError as e:
            raise InvalidApiKeyError() from e
        except openai.PermissionDeniedError as e:
            raise ProviderBillingError() from e
        except openai.OpenAIError as e:
            logger.info("openai ping failed: %s", type(e).__name__)
            raise ProviderUnavailableError() from e

    async def enhance_copy(
        self,
        *,
        system_prompt: str,
        user_message: str,
        timeout_seconds: float,
    ) -> EnhancedCopyResult:
        client = AsyncOpenAI(api_key=self._api_key.get_secret_value())
        try:
            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=self._model,
                    max_tokens=512,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message},
                    ],
                ),
                timeout=timeout_seconds,
            )
            content = response.choices[0].message.content
            if not content:
                raise ValueError("no content in response")
            parsed = json.loads(content)
            return EnhancedCopyResult(
                title=str(parsed["title"]).strip(),
                summary=str(parsed["summary"]).strip(),
                used_llm=True,
            )
        except (
            TimeoutError,
            openai.OpenAIError,
            ValueError,
            KeyError,
            json.JSONDecodeError,
        ) as exc:
            logger.info("openai enhance failed: %s", type(exc).__name__)
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
        client = AsyncOpenAI(api_key=self._api_key.get_secret_value())
        tool_specs = [_to_openai_tool(t) for t in tools]
        # OpenAI takes the system prompt as the first message.
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
        msgs.extend(messages)
        start = time.monotonic()
        tool_call_count = 0

        for turn in range(max_tool_calls + 1):
            if time.monotonic() - start > max_duration_seconds:
                yield DoneEvent(turns_used=turn, stop_reason="timeout")
                return

            # Per-turn collectors. Tool calls arrive as deltas indexed by
            # position within the response; OpenAI doesn't promise IDs are
            # delivered before arguments, so we accumulate both.
            tool_calls_by_index: dict[int, dict[str, Any]] = {}
            finish_reason: str | None = None
            assistant_text = ""

            stream = await client.chat.completions.create(
                model=self._model,
                messages=msgs,  # type: ignore[arg-type]
                tools=tool_specs,  # type: ignore[arg-type]
                stream=True,
            )
            # `stream=True` returns an AsyncStream, not a single completion;
            # mypy sees the union type but can't narrow without an assertion.
            assert hasattr(stream, "__aiter__"), "stream=True should return AsyncStream"
            async for chunk in stream:
                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = choice.delta
                if delta.content:
                    yield TokenEvent(text=delta.content)
                    assistant_text += delta.content
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        bucket = tool_calls_by_index.setdefault(
                            idx,
                            {"id": "", "name": "", "arguments": ""},
                        )
                        if tc_delta.id:
                            bucket["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            bucket["name"] = tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            bucket["arguments"] += tc_delta.function.arguments
                if choice.finish_reason:
                    finish_reason = choice.finish_reason

            if finish_reason in ("stop", "length"):
                yield DoneEvent(turns_used=turn + 1, stop_reason="end_turn")
                return
            if finish_reason != "tool_calls":
                yield DoneEvent(turns_used=turn + 1, stop_reason=str(finish_reason or "unknown"))
                return

            # Surface the assistant's tool_calls in the conversation history
            # exactly as OpenAI expects to see it on the next call.
            pending = []
            for idx in sorted(tool_calls_by_index.keys()):
                bucket = tool_calls_by_index[idx]
                try:
                    args = json.loads(bucket["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                yield ToolUseEvent(id=bucket["id"], tool=bucket["name"], input=args)
                pending.append({"id": bucket["id"], "name": bucket["name"], "input": args})

            msgs.append(
                {
                    "role": "assistant",
                    "content": assistant_text or None,
                    "tool_calls": [
                        {
                            "id": p["id"],
                            "type": "function",
                            "function": {
                                "name": p["name"],
                                "arguments": json.dumps(p["input"], default=str),
                            },
                        }
                        for p in pending
                    ],
                }
            )

            for p in pending:
                tool_call_count += 1
                if tool_call_count > max_tool_calls:
                    yield DoneEvent(turns_used=turn + 1, stop_reason="max_tool_calls")
                    return
                output, is_error = await tool_dispatcher(p["name"], p["input"])
                yield ToolResultEvent(id=p["id"], output=output, is_error=is_error)
                msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": p["id"],
                        "content": output if is_error else json.dumps(output, default=str),
                    }
                )

        yield DoneEvent(turns_used=max_tool_calls, stop_reason="max_tool_calls")


def _to_openai_tool(spec: ToolSpec) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": spec.name,
            "description": spec.description,
            "parameters": spec.parameters_schema,
        },
    }
