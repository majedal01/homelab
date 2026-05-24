"""LLM-based copy enhancement for insights.

Each generator may call `enhance_copy` to rewrite title/summary into
warmer prose. The call is gated on the provided Anthropic key, has a
hard timeout, and falls back silently to the deterministic copy on any
failure so the generator's run still counts as successful.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import anthropic
from pydantic import SecretStr

logger = logging.getLogger(__name__)

# Hard cap so a slow upstream cannot pile up requests against the agent loop.
LLM_TIMEOUT_SECONDS: float = 5.0
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
    model: str = DEFAULT_MODEL,
) -> EnhancedCopy:
    """Try to rewrite (title, summary). Always returns; never raises."""
    if anthropic_key is None:
        return EnhancedCopy(title=fallback_title, summary=fallback_summary, used_llm=False)

    user_message = json.dumps(
        {
            "card_type": card_type,
            "fallback_title": fallback_title,
            "fallback_summary": fallback_summary,
            "payload": payload,
        },
        default=str,
    )

    try:
        client = anthropic.AsyncAnthropic(api_key=anthropic_key.get_secret_value())
        response = await asyncio.wait_for(
            client.messages.create(
                model=model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        text_block = next(
            (b for b in response.content if isinstance(b, anthropic.types.TextBlock)),
            None,
        )
        if text_block is None:
            raise ValueError("no text block in response")
        parsed = json.loads(text_block.text)
        title = str(parsed["title"]).strip()
        summary = str(parsed["summary"]).strip()
        if not title or not summary:
            raise ValueError("empty title or summary from LLM")
    except (TimeoutError, anthropic.APIError, ValueError, KeyError, json.JSONDecodeError) as exc:
        logger.info("llm enhancement skipped (%s): %s", card_type, type(exc).__name__)
        return EnhancedCopy(title=fallback_title, summary=fallback_summary, used_llm=False)

    return EnhancedCopy(title=title, summary=summary, used_llm=True)
