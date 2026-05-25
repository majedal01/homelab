"""Provider-agnostic LLM abstraction.

Concrete providers (anthropic_provider, openai_provider) implement two
methods: `enhance_copy()` for single-shot JSON-out completion, and
`stream_agent()` for the streaming tool-use loop.

Both providers normalize their native streaming events into the same
`StreamEvent` union so the SSE wire format stays stable.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, SecretStr

# (tool_name, tool_input) -> (output, is_error)
ToolDispatcher = Callable[[str, dict[str, Any]], Awaitable[tuple[Any, bool]]]

Provider = Literal["anthropic", "openai"]


@dataclass(frozen=True)
class EnhancedCopyResult:
    """What enhance_copy returns. Mirrors EnhancedCopy in app/insights/llm.py;
    the older shape stays in place as an internal type the call sites still
    consume so v2.6d doesn't ripple into card components."""

    title: str
    summary: str
    used_llm: bool


@dataclass(frozen=True)
class ToolSpec:
    """Provider-neutral tool description.

    `parameters_schema` is a JSON Schema dict. Anthropic uses it directly
    as `input_schema`; OpenAI nests it under `function.parameters`. The
    schema itself is shared because Pydantic emits JSON Schema both
    providers accept.
    """

    name: str
    description: str
    parameters_schema: dict[str, Any]


# --- streaming event union --------------------------------------------------

# Each provider parses its own native streaming events and yields one of
# these. The Ask router re-emits them as `event: <type>` SSE frames in
# the same shape the v2.5 frontend already parses.


class TokenEvent(BaseModel):
    type: Literal["token"] = "token"
    text: str


class ToolUseEvent(BaseModel):
    type: Literal["tool_use"] = "tool_use"
    id: str
    tool: str
    input: dict[str, Any]


class ToolResultEvent(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    id: str
    output: Any
    is_error: bool


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    turns_used: int
    stop_reason: str


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str


StreamEvent = TokenEvent | ToolUseEvent | ToolResultEvent | DoneEvent | ErrorEvent


# --- abstract provider ------------------------------------------------------


class LlmProvider(ABC):
    """Two methods. Concrete providers handle their own SDK + format quirks
    behind these signatures.

    `ping()` is used by `POST /api/session` to validate the user's key
    before storing it; cheapest meaningful call per provider.
    """

    name: Provider

    def __init__(self, api_key: SecretStr, model: str) -> None:
        self._api_key = api_key
        self._model = model

    @abstractmethod
    async def ping(self) -> None:
        """Single tiny completion to validate the key. Raises on failure
        with the same `LlmProviderError` taxonomy callers expect."""

    @abstractmethod
    async def enhance_copy(
        self,
        *,
        system_prompt: str,
        user_message: str,
        timeout_seconds: float,
    ) -> EnhancedCopyResult:
        """Single-shot JSON-out completion. Returns deterministic-fallback
        copy on any failure (caller supplies the fallback)."""

    @abstractmethod
    def stream_agent(
        self,
        *,
        system_prompt: str,
        messages: list[dict[str, Any]],
        tools: list[ToolSpec],
        tool_dispatcher: ToolDispatcher,
        max_tool_calls: int,
        max_duration_seconds: int,
    ) -> AsyncIterator[StreamEvent]:
        """Run the full tool-use loop. Provider yields normalized stream
        events; when the model calls a tool, the provider invokes
        `tool_dispatcher(name, input)` and feeds the result back into
        the conversation in the provider's native format.

        Caller (`app/agent/stream.py`) just pumps events to SSE. Caller
        does not need to know any provider-specific tool-call shape."""


# --- error taxonomy ---------------------------------------------------------


class LlmProviderError(Exception):
    """Base for provider errors. Subclasses carry the specific failure code
    used by the session validation flow's error mapping."""

    code: str
    http_status: int


class InvalidApiKeyError(LlmProviderError):
    code = "invalid_api_key"
    http_status = 401


class ProviderBillingError(LlmProviderError):
    code = "billing"
    http_status = 402


class ProviderUnavailableError(LlmProviderError):
    code = "unavailable"
    http_status = 502
