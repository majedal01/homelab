"""LLM provider abstraction.

v2.6d introduces multi-provider support (Anthropic + OpenAI) for both
the insights enhance-copy path and the streaming tool-use Ask agent.
Callers (`app/insights/llm.py`, `app/agent/`, `app/routers/session.py`)
go through `resolve_provider()` rather than calling the Anthropic or
OpenAI SDK directly.

The wire format that reaches the browser (`event: token`, `event: tool_use`,
`event: tool_result`, `event: done`, `event: error`) does NOT change.
Each provider normalizes its native streaming events into the same
`StreamEvent` types defined in `base.py`.
"""

from app.llm.base import (
    DoneEvent,
    EnhancedCopyResult,
    ErrorEvent,
    InvalidApiKeyError,
    LlmProvider,
    LlmProviderError,
    Provider,
    ProviderBillingError,
    ProviderUnavailableError,
    StreamEvent,
    TokenEvent,
    ToolResultEvent,
    ToolSpec,
    ToolUseEvent,
)
from app.llm.detect import (
    ALLOWED_MODELS,
    DEFAULT_MODEL_FOR_PROVIDER,
    MODEL_CATALOG,
    ModelOption,
    detect_provider,
)
from app.llm.registry import build_provider

__all__ = [
    "ALLOWED_MODELS",
    "DEFAULT_MODEL_FOR_PROVIDER",
    "MODEL_CATALOG",
    "ModelOption",
    "DoneEvent",
    "EnhancedCopyResult",
    "ErrorEvent",
    "InvalidApiKeyError",
    "LlmProvider",
    "LlmProviderError",
    "Provider",
    "ProviderBillingError",
    "ProviderUnavailableError",
    "StreamEvent",
    "TokenEvent",
    "ToolResultEvent",
    "ToolSpec",
    "ToolUseEvent",
    "build_provider",
    "detect_provider",
]
