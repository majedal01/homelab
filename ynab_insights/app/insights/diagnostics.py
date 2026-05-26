"""Generator-internal diagnostic logging.

Turn-on switch: `LOG_GENERATOR_INTERNALS=true` in the process env. When off
(the default), `diag(...)` is a cheap no-op — the env lookup is cached on
first call. When on, each call emits one INFO-level structured line to a
dedicated logger so prod can filter cleanly:

    generator=subscription_audit event=candidate_payees count=27

Used to diagnose "why did this generator produce zero" without dropping
into pdb on a stage VM. Keep call sites at meaningful filter steps —
"how many candidates did we start with, where did they drop." Avoid
logging payee names or amounts; we don't want PII leaking via stage logs.
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Any

logger = logging.getLogger("app.insights.diagnostics")

_TRUTHY = frozenset({"1", "true", "yes", "on"})


@lru_cache(maxsize=1)
def _enabled() -> bool:
    return os.environ.get("LOG_GENERATOR_INTERNALS", "").strip().lower() in _TRUTHY


def reset_for_tests() -> None:
    """Drop the cached env lookup. Pytest fixtures call this when they
    mutate LOG_GENERATOR_INTERNALS between tests."""
    _enabled.cache_clear()


def diag(generator: str, event: str, /, **fields: Any) -> None:
    """Emit one structured diagnostic line if the env switch is on.

    `generator` is the card_type slug. `event` is a short kebab-case
    label for the step. Fields are appended as `k=v` pairs in insertion
    order. Don't pass anything sensitive — these lines land in stage
    container logs.
    """
    if not _enabled():
        return
    if fields:
        formatted = " ".join(f"{k}={fields[k]}" for k in fields)
        logger.info("generator=%s event=%s %s", generator, event, formatted)
    else:
        logger.info("generator=%s event=%s", generator, event)
