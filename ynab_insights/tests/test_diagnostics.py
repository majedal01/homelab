"""Diagnostic logging is gated on LOG_GENERATOR_INTERNALS.

Avoids leaking debug detail into prod logs by default while still being
trivially toggleable on stage. Tests cover the no-op default and the
opt-in shape; generator-specific call counts aren't worth asserting (they
churn with feature work).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

from app.insights import diagnostics


@pytest.fixture(autouse=True)
def _reset_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Ensure each test starts with a fresh env lookup."""
    monkeypatch.delenv("LOG_GENERATOR_INTERNALS", raising=False)
    diagnostics.reset_for_tests()
    yield
    diagnostics.reset_for_tests()


def test_disabled_by_default(caplog: pytest.LogCaptureFixture) -> None:
    """No env var = no log record."""
    with caplog.at_level(logging.INFO, logger="app.insights.diagnostics"):
        diagnostics.diag("sub", "step", count=5)
    assert caplog.records == []


def test_enabled_emits_one_record(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setenv("LOG_GENERATOR_INTERNALS", "true")
    diagnostics.reset_for_tests()
    with caplog.at_level(logging.INFO, logger="app.insights.diagnostics"):
        diagnostics.diag("sub", "step", count=5, reason="ok")
    assert len(caplog.records) == 1
    message = caplog.records[0].getMessage()
    assert "generator=sub" in message
    assert "event=step" in message
    assert "count=5" in message
    assert "reason=ok" in message


def test_disabled_lookup_short_circuits_field_formatting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When off, diag should not format its kwargs — verify by passing an
    object whose repr would raise."""
    monkeypatch.delenv("LOG_GENERATOR_INTERNALS", raising=False)
    diagnostics.reset_for_tests()

    class Boom:
        def __repr__(self) -> str:
            raise RuntimeError("should not be called")

    diagnostics.diag("sub", "step", suspect=Boom())
