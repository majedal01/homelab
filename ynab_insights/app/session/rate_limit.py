"""Per-session (and per-IP for unauthenticated) rate limiting.

Token-bucket implemented in memory, scoped to the same TTLCache lifetime
as sessions. Different endpoint groups have different ceilings; the
mapping lives in `RULES` below.

When a bucket is exhausted, the middleware returns 429 with a clear
`{"error": "rate_limited", "scope": str, "retry_after_seconds": int}`
body so the frontend can render a targeted toast.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from cachetools import TTLCache
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from app.config import Settings
from app.observability import metrics


@dataclass
class _Rule:
    scope: str  # for the 429 body
    limit_per_window: int
    window_seconds: int


def _rules(settings: Settings) -> dict[tuple[str, str], _Rule]:
    """Map (method, prefix) -> rule. Most-specific prefix wins, so deeper
    paths (like /api/session/demo) must come before their parent prefix
    (/api/session). `_match` returns the first matching rule."""
    h = 3600
    m = 60
    return {
        # Public demo endpoint: per-IP. Capped tighter than authed routes
        # because the visitor has no session cookie yet.
        ("POST", "/api/session/demo"): _Rule(
            "demo_session_create",
            settings.demo_session_rate_limit_per_ip_per_hour,
            h,
        ),
        ("POST", "/api/session/budget"): _Rule(
            "snapshot", settings.rate_limit_snapshot_per_hour, h
        ),
        ("POST", "/api/session/refresh"): _Rule(
            "snapshot", settings.rate_limit_snapshot_per_hour, h
        ),
        ("POST", "/api/session"): _Rule(
            "session_create", settings.rate_limit_session_create_per_hour, h
        ),
        ("POST", "/api/insights/generate"): _Rule(
            "generate", settings.rate_limit_generate_per_hour, h
        ),
        ("POST", "/ask"): _Rule("ask", settings.rate_limit_ask_per_hour, h),
        ("GET", "/api/"): _Rule("reads", settings.rate_limit_reads_per_minute, m),
    }


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket per (bucket_key, scope)."""

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._rules = _rules(settings)
        # Buckets evict after twice the longest window; cap at 10k entries.
        self._buckets: TTLCache[tuple[str, str], list[float]] = TTLCache(
            maxsize=10_000, ttl=2 * 3600
        )

    def _match(self, method: str, path: str) -> _Rule | None:
        # Most-specific prefix wins; rules dict iterates in declaration order,
        # so list the specific prefixes first (we do above).
        for (m, prefix), rule in self._rules.items():
            if method == m and path.startswith(prefix):
                return rule
        return None

    def _bucket_key(self, request: Request, rule: _Rule) -> str:
        # Authenticated requests bucket by sid; unauthenticated by client IP.
        sess = getattr(request.state, "session", None)
        if sess is not None:
            return f"sid:{sess.sid}"
        client = request.client.host if request.client else "unknown"
        return f"ip:{client}"

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rule = self._match(request.method, request.url.path)
        if rule is None:
            return await call_next(request)

        now = time.monotonic()
        key = (self._bucket_key(request, rule), rule.scope)
        events = self._buckets.get(key) or []
        events = [t for t in events if now - t < rule.window_seconds]
        if len(events) >= rule.limit_per_window:
            metrics.rate_limit_hits_total.labels(scope=rule.scope).inc()
            retry_after = int(rule.window_seconds - (now - events[0]))
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limited",
                    "scope": rule.scope,
                    "retry_after_seconds": max(retry_after, 1),
                },
                headers={"Retry-After": str(max(retry_after, 1))},
            )
        events.append(now)
        self._buckets[key] = events
        return await call_next(request)
