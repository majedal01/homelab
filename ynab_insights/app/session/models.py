"""Session-layer Pydantic models.

`UserSession` holds the per-user state for the v2.5 zero-persistence model:
tokens, the YNAB data snapshot, generated insights, and timestamps. Tokens
use `SecretStr` so they're redacted from `repr()` / `model_dump()` by
default; explicit access goes through `.get_secret_value()`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.snapshot.models import YnabSnapshot


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UserSession(BaseModel):
    """One signed-in user, scoped to one budget, held in memory."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    sid: str
    ynab_token: SecretStr
    anthropic_key: SecretStr
    budget_id: str | None = None
    budget_name: str | None = None
    snapshot: YnabSnapshot | None = None
    insights: list[Any] = Field(default_factory=list)
    runs: list[Any] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utcnow)
    last_active_at: datetime = Field(default_factory=_utcnow)
    last_synced_at: datetime | None = None

    def touch(self) -> None:
        """Bump `last_active_at`. Called by middleware on every authed request."""
        self.last_active_at = _utcnow()


class SessionPublic(BaseModel):
    """Response shape for `GET /api/session`. Tokens never appear here."""

    sid: str
    budget_id: str | None
    budget_name: str | None
    created_at: datetime
    last_active_at: datetime
    last_synced_at: datetime | None
    expires_at: datetime


# Resolve forward refs at import time so Pydantic can build the model
# even with `from __future__ import annotations` in effect. Without this,
# FastAPI's `get_type_hints()` raises across the whole module and routes
# defined elsewhere misclassify their parameters (e.g. starlette.Request
# gets treated as a request body, returning 422).
UserSession.model_rebuild()
