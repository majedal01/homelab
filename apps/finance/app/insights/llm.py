"""LLM-based copy enhancement for insights.

Routes through the v2.6d provider abstraction so a session with an
OpenAI key works identically to one with an Anthropic key. Both
providers return `EnhancedCopyResult` (LLM-enhanced or fallback);
this module turns the result into the legacy `EnhancedCopy` shape
the generators expect.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from pydantic import SecretStr

from app.llm import DEFAULT_MODEL_FOR_PROVIDER, Provider, build_provider, detect_provider

logger = logging.getLogger(__name__)

# Hard cap so a slow upstream cannot pile up requests against the agent loop.
LLM_TIMEOUT_SECONDS: float = 5.0

# Backwards-compat name; the model that callers without a session pick fall
# back to. New v2.6d code passes (key, provider, model) explicitly.
DEFAULT_MODEL = "claude-haiku-4-5-20251001"


@dataclass(frozen=True)
class EnhancedCopy:
    title: str
    summary: str
    used_llm: bool


SYSTEM_PROMPT = (
    "You are a warm but concise personal finance coach writing one card for "
    "a user's insights feed. You receive a structured payload describing the "
    'insight; respond with a JSON object {"title": str, "summary": str}. '
    "Title: at most 60 characters, no trailing punctuation, no emoji. "
    "Summary: 1-2 sentences, plain prose, under 280 characters, no emoji, "
    "no markdown. Do not invent numbers; only reuse the figures in the "
    "payload. Speak in second person."
)


async def enhance_copy(
    *,
    anthropic_key: SecretStr | None,
    fallback_title: str,
    fallback_summary: str,
    card_type: str,
    payload: dict[str, Any],
    model: str | None = None,
    provider: Provider | None = None,
) -> EnhancedCopy:
    """Try to rewrite (title, summary). Always returns; never raises.

    `anthropic_key` is a misnomer in v2.6d — it may be an OpenAI key too;
    the parameter name is preserved so existing call sites don't churn.
    If `provider` is None, we infer from the key's prefix.
    """
    if anthropic_key is None:
        return EnhancedCopy(title=fallback_title, summary=fallback_summary, used_llm=False)

    key_value = anthropic_key.get_secret_value()
    inferred = provider or detect_provider(key_value)
    if inferred is None:
        return EnhancedCopy(title=fallback_title, summary=fallback_summary, used_llm=False)

    resolved_model = model or DEFAULT_MODEL_FOR_PROVIDER[inferred]
    user_message = json.dumps(
        {
            "card_type": card_type,
            "fallback_title": fallback_title,
            "fallback_summary": fallback_summary,
            "payload": payload,
        },
        default=str,
    )

    llm = build_provider(inferred, anthropic_key, resolved_model)
    result = await llm.enhance_copy(
        system_prompt=SYSTEM_PROMPT,
        user_message=user_message,
        timeout_seconds=LLM_TIMEOUT_SECONDS,
    )
    if not result.used_llm or not result.title or not result.summary:
        return EnhancedCopy(title=fallback_title, summary=fallback_summary, used_llm=False)
    return EnhancedCopy(title=result.title, summary=result.summary, used_llm=True)
