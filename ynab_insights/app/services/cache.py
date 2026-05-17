"""Tiny in-memory TTL cache for hot read paths.

Not safe for cross-process state; we're a single uvicorn worker. Cache
invalidation on writes is intentionally absent — entries simply expire after
their TTL. For sync-heavy workloads this means dashboard data may lag by up
to one TTL window after a fresh sync, which is acceptable for personal
budgeting.
"""

from __future__ import annotations

import time
from collections.abc import Hashable


class TTLCache[V]:
    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._store: dict[Hashable, tuple[float, V]] = {}

    def get(self, key: Hashable) -> V | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: Hashable, value: V) -> None:
        self._store[key] = (time.monotonic() + self._ttl, value)

    def clear(self) -> None:
        self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)
