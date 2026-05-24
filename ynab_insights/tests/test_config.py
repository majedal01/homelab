"""Settings validation behavior."""

from __future__ import annotations

import pytest

from app.config import Settings


def _build(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    """Construct a fresh Settings with the given env overlay applied."""
    monkeypatch.setenv("APP_ENV", "stage")
    monkeypatch.setenv("APP_VERSION", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
    monkeypatch.setenv("SYNC_INTERVAL_MINUTES", "0")
    monkeypatch.setenv("INSIGHTS_GENERATION_ENABLED", "false")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


def test_empty_anthropic_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # docker compose's `${VAR:-}` substitution becomes "" in the container
    # when the host env var is unset. The Optional contract must hold so
    # downstream `is None` guards work.
    s = _build(monkeypatch, ANTHROPIC_API_KEY="")
    assert s.anthropic_api_key is None


def test_whitespace_anthropic_key_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _build(monkeypatch, ANTHROPIC_API_KEY="   ")
    assert s.anthropic_api_key is None


def test_real_anthropic_key_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _build(monkeypatch, ANTHROPIC_API_KEY="sk-ant-real-value")
    assert s.anthropic_api_key == "sk-ant-real-value"


def test_empty_ynab_token_is_none(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _build(monkeypatch, YNAB_TOKEN="")
    assert s.ynab_token is None
