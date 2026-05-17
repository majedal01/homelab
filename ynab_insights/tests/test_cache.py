"""Tests for the TTLCache."""

import time

from app.services.cache import TTLCache


def test_get_returns_none_for_unknown_key() -> None:
    cache: TTLCache[int] = TTLCache(ttl_seconds=60.0)
    assert cache.get("missing") is None


def test_set_then_get_within_ttl() -> None:
    cache: TTLCache[int] = TTLCache(ttl_seconds=60.0)
    cache.set("k", 42)
    assert cache.get("k") == 42
    assert cache.size == 1


def test_entries_expire_after_ttl() -> None:
    cache: TTLCache[int] = TTLCache(ttl_seconds=0.05)  # 50ms
    cache.set("k", 1)
    assert cache.get("k") == 1
    time.sleep(0.1)
    assert cache.get("k") is None
    # Lazy-deleted on get; size goes back to 0
    assert cache.size == 0


def test_clear_removes_everything() -> None:
    cache: TTLCache[int] = TTLCache(ttl_seconds=60.0)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.clear()
    assert cache.size == 0
    assert cache.get("a") is None
