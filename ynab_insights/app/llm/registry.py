"""Provider factory.

Stays separate from `__init__.py` so circular imports between
base/anthropic_provider/openai_provider stay easy to reason about.
"""

from __future__ import annotations

from pydantic import SecretStr

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LlmProvider, Provider
from app.llm.openai_provider import OpenAIProvider


def build_provider(provider: Provider, api_key: SecretStr, model: str) -> LlmProvider:
    if provider == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model)
    if provider == "openai":
        return OpenAIProvider(api_key=api_key, model=model)
    raise ValueError(f"unknown provider: {provider!r}")
