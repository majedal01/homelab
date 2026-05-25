"""TTL-evicted in-memory session store.

Wraps `cachetools.TTLCache` so callers don't depend on the implementation.
The cache is process-local; horizontal scaling requires Redis (out of scope
for v2.5).

`maxsize` caps memory under attack: at ~5-10MB per session the 500-session
ceiling sits comfortably under a 2GB VM. LRU eviction kicks the oldest idle
session when the cap is hit, which is the right default for personal use.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache
from threading import Lock

from cachetools import TTLCache
from itsdangerous import BadSignature, URLSafeSerializer

from app.config import Settings
from app.observability import metrics
from app.session.models import UserSession

logger = logging.getLogger(__name__)

# Defaults; overridable via Settings in tests / per-env tuning.
DEFAULT_MAXSIZE = 500
DEFAULT_IDLE_TTL_SECONDS = 3600  # 1h idle
DEFAULT_ABSOLUTE_TTL_SECONDS = 14400  # 4h hard cap
COOKIE_NAME = "sid"
COOKIE_SALT = "ynab-insights.session.v1"


class SessionStore:
    """In-memory session store with TTL eviction and a signed-cookie codec."""

    def __init__(
        self,
        *,
        secret_key: str,
        maxsize: int = DEFAULT_MAXSIZE,
        idle_ttl_seconds: int = DEFAULT_IDLE_TTL_SECONDS,
        absolute_ttl_seconds: int = DEFAULT_ABSOLUTE_TTL_SECONDS,
    ) -> None:
        self._cache: TTLCache[str, UserSession] = TTLCache(
            maxsize=maxsize,
            ttl=idle_ttl_seconds,
        )
        self._lock = Lock()
        self._serializer = URLSafeSerializer(secret_key, salt=COOKIE_SALT)
        self._idle_ttl = idle_ttl_seconds
        self._absolute_ttl = absolute_ttl_seconds

    # --- lifecycle ----------------------------------------------------------

    def create(self, session: UserSession) -> None:
        with self._lock:
            self._cache[session.sid] = session

    def get(self, sid: str) -> UserSession | None:
        with self._lock:
            session: UserSession | None = self._cache.get(sid)
            if session is None:
                return None
            # Re-insert to bump the idle TTL window. TTLCache pins the
            # expiry at insertion time; reading does not extend it.
            self._cache[sid] = session
            session.touch()
            if self.is_past_absolute_cap(session):
                # 4h hard cap reached; evict.
                del self._cache[sid]
                metrics.sessions_evicted_total.labels(reason="absolute_cap").inc()
                if session.is_demo:
                    metrics.demo_session_active.dec()
                return None
            return session

    def evict(self, sid: str) -> None:
        with self._lock:
            session = self._cache.pop(sid, None)
        if session is not None:
            metrics.sessions_evicted_total.labels(reason="explicit_delete").inc()
            if session.is_demo:
                metrics.demo_session_active.dec()

    def __len__(self) -> int:
        return len(self._cache)

    # --- helpers ------------------------------------------------------------

    def is_past_absolute_cap(self, session: UserSession) -> bool:
        return datetime.now(UTC) - session.created_at > timedelta(seconds=self._absolute_ttl)

    def expires_at(self, session: UserSession) -> datetime:
        """Wall-clock expiry: whichever of (idle TTL, absolute cap) comes first."""
        idle = session.last_active_at + timedelta(seconds=self._idle_ttl)
        absolute = session.created_at + timedelta(seconds=self._absolute_ttl)
        return min(idle, absolute)

    # --- cookie codec -------------------------------------------------------

    def sign(self, sid: str) -> str:
        return str(self._serializer.dumps(sid))

    def unsign(self, signed: str) -> str | None:
        try:
            value = self._serializer.loads(signed)
        except BadSignature:
            return None
        return value if isinstance(value, str) else None

    @property
    def cookie_max_age(self) -> int:
        return self._absolute_ttl


def new_sid() -> str:
    """Cryptographically random session ID. URL-safe for cookies."""
    return secrets.token_urlsafe(32)


@lru_cache
def get_session_store() -> SessionStore:
    """Process-wide singleton. FastAPI dependency-injects this."""
    settings = _resolve_settings()
    return SessionStore(secret_key=settings.session_secret_key)


def _resolve_settings() -> Settings:
    # Indirected so test code can monkeypatch Settings without breaking imports.
    from app.config import get_settings

    return get_settings()
