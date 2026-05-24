"""Settings validation (v2.5)."""

from __future__ import annotations

import pytest

from app.config import Settings


def _build(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    monkeypatch.setenv("APP_ENV", "stage")
    monkeypatch.setenv("APP_VERSION", "test")
    monkeypatch.setenv("SESSION_SECRET_KEY", "test-secret")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _build(monkeypatch)
    assert s.app_env == "stage"
    assert s.session_secret_key == "test-secret"
    # Defaults documented in DESIGN/planning doc.
    assert s.agent_max_tool_calls == 20
    assert s.agent_max_duration_seconds == 60
    assert s.agent_input_max_chars == 1000


def test_rate_limit_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    s = _build(
        monkeypatch,
        RATE_LIMIT_ASK_PER_HOUR="60",
        RATE_LIMIT_GENERATE_PER_HOUR="20",
    )
    assert s.rate_limit_ask_per_hour == 60
    assert s.rate_limit_generate_per_hour == 20
