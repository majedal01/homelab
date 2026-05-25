"""Provider detection from API key prefix + per-provider model lists.

Anthropic: `sk-ant-`. OpenAI: `sk-` (optionally `sk-proj-` for the new
project-scoped keys). Anything else returns None and the session router
turns that into a 400.
"""

from __future__ import annotations

import re
from typing import Final

from app.llm.base import Provider

# Keep these regexes loose enough to accept new tail-byte schemes Anthropic /
# OpenAI introduce, but tight enough to catch obvious paste mistakes (random
# strings, wrong-provider keys).
_ANTHROPIC_KEY_RE: Final = re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,256}$")
_OPENAI_KEY_RE: Final = re.compile(r"^sk-(proj-)?[A-Za-z0-9_-]{20,256}$")

# Per-provider model allow-lists. Frontend dropdown mirrors these.
ALLOWED_MODELS: Final[dict[Provider, frozenset[str]]] = {
    "anthropic": frozenset(
        {
            "claude-opus-4-7",
            "claude-sonnet-4-6",
            "claude-haiku-4-5-20251001",
        }
    ),
    "openai": frozenset(
        {
            "gpt-5",
            "gpt-5-mini",
            "o4-mini",
        }
    ),
}

DEFAULT_MODEL_FOR_PROVIDER: Final[dict[Provider, str]] = {
    "anthropic": "claude-haiku-4-5-20251001",
    "openai": "gpt-5-mini",
}


def detect_provider(key: str) -> Provider | None:
    """Map a raw API key to its provider. None on no match.

    Anthropic is checked first because `sk-ant-…` also matches the looser
    OpenAI pattern. Ordering matters.
    """
    if _ANTHROPIC_KEY_RE.match(key):
        return "anthropic"
    if _OPENAI_KEY_RE.match(key):
        return "openai"
    return None
