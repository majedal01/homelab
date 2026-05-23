"""LLM-based copy enhancement for insights.

Each generator can call `enhance_copy` to rewrite the title/summary of its
deterministic output into warmer language. The call is gated on
`anthropic_api_key`, has a hard timeout, and falls back silently to the
deterministic copy on any failure so the generator's run still counts as
successful.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any

import anthropic

from app.config import Settings

logger = logging.getLogger(__name__)

# Single Anthropic call per insight is cheap; cap aggressively so a slow
# upstream cannot pile up jobs against the scheduler's max_instances=1.
LLM_TIMEOUT_SECONDS: float = 5.0


@dataclass(frozen=True)
class EnhancedCopy:
    title: str
    summary: str
    used_llm: bool


SYSTEM_PROMPT = (
    "You are a warm but concise personal finance coach writing one card for "
    "a user's insights feed. You receive a structured payload describing the "
    "insight; respond with a JSON object {\"title\": str, \"summary\": str}. "
    "Title: at most 60 characters, no trailing punctuation, no emoji. "
    "Summary: 1-2 sentences, plain prose, under 280 characters, no emoji, "
    "no markdown. Do not invent numbers; only reuse the figures in the "
    "payload. Speak in second person."
)


async def enhance_copy(
    *,
    settings: Settings,
    fallback_title: str,
    fallback_summary: str,
    card_type: str,
    payload: dict[str, Any],
) -> EnhancedCopy:
    """Try to rewrite (title, summary) for an insight. Always returns a result.

    Falls back to the deterministic copy whenever the API key is missing,
    the call times out, the response is unparseable, or any other error
    occurs. The generator decides whether the result was LLM-touched via
    `used_llm`.
    """
    if settings.anthropic_api_key is None:
        return EnhancedCopy(
            title=fallback_title, summary=fallback_summary, used_llm=False
        )

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
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response = await asyncio.wait_for(
            client.messages.create(
                model=settings.anthropic_model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}],
            ),
            timeout=LLM_TIMEOUT_SECONDS,
        )
        text_block = next(
            (b for b in response.content if getattr(b, "type", None) == "text"),
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
        logger.info("llm enhancement skipped (%s): %s", card_type, exc)
        return EnhancedCopy(
            title=fallback_title, summary=fallback_summary, used_llm=False
        )

    return EnhancedCopy(title=title, summary=summary, used_llm=True)
