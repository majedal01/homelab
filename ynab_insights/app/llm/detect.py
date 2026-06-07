"""Provider detection from API key prefix + per-provider model lists.

Anthropic: `sk-ant-`. OpenAI: `sk-` (optionally `sk-proj-` for the new
project-scoped keys). Anything else returns None and the session router
turns that into a 400.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from app.llm.base import Provider

# Keep these regexes loose enough to accept new tail-byte schemes Anthropic /
# OpenAI introduce, but tight enough to catch obvious paste mistakes (random
# strings, wrong-provider keys).
_ANTHROPIC_KEY_RE: Final = re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,256}$")
_OPENAI_KEY_RE: Final = re.compile(r"^sk-(proj-)?[A-Za-z0-9_-]{20,256}$")


@dataclass(frozen=True)
class ModelOption:
    """One selectable model: the API id plus display copy for the picker."""

    value: str
    label: str
    tagline: str


# Single source of truth for selectable models per provider. The first entry
# per provider is the default the picker preselects. The session router
# validates against this and the frontend fetches it via GET
# /api/session/models, so there is no hand-maintained mirror to go stale.
MODEL_CATALOG: Final[dict[Provider, tuple[ModelOption, ...]]] = {
    "anthropic": (
        ModelOption(
            "claude-haiku-4-5-20251001", "Haiku 4.5", "Fast and inexpensive. Good default."
        ),
        ModelOption("claude-sonnet-4-6", "Sonnet 4.6", "Balanced for the LLM-narrated cards."),
        ModelOption("claude-opus-4-8", "Opus 4.8", "Most capable. Slower and pricier."),
    ),
    "openai": (
        ModelOption("gpt-5-mini", "GPT-5 mini", "Fast and inexpensive. Good default."),
        ModelOption("gpt-5", "GPT-5", "Balanced for the LLM-narrated cards."),
        ModelOption("o4-mini", "o4-mini", "Reasoning model. Slower but thorough."),
    ),
}

# Derived from the catalog so validation, defaults, and the picker can't drift.
ALLOWED_MODELS: Final[dict[Provider, frozenset[str]]] = {
    provider: frozenset(option.value for option in options)
    for provider, options in MODEL_CATALOG.items()
}

DEFAULT_MODEL_FOR_PROVIDER: Final[dict[Provider, str]] = {
    provider: options[0].value for provider, options in MODEL_CATALOG.items()
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
