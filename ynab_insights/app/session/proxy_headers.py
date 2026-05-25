"""Defensive logging when a request bypasses the expected reverse proxy.

The Cloudflare Tunnel running on the VM terminates TLS and sets
`X-Forwarded-Proto: https` on every request. The session-create cookie
relies on that header to set the `Secure` flag correctly. If the tunnel
ever stops setting it (misconfig, direct hits to the container port, an
override gone wrong), the app would silently emit non-Secure cookies on
HTTPS responses and the issue would be invisible.

This middleware doesn't reject anything. It just emits a single log
warning per minute when `REQUIRE_PROXY_HEADERS=true` and a request
arrives without `X-Forwarded-Proto`. Enough to catch a misconfig in
deploys without breaking the app for users on the next request.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# One warning per minute to avoid log spam if many requests bypass the proxy.
_LAST_WARN_AT: dict[str, float] = {}
_WARN_INTERVAL_S = 60.0


class ProxyHeaderMiddleware(BaseHTTPMiddleware):
    """No-op pass-through that warns when X-Forwarded-Proto is missing.

    Constructor takes `require_proxy_headers: bool` so the middleware is
    a no-op outside stage / prod and we don't have to add it conditionally
    in `main.py`.
    """

    def __init__(self, app: ASGIApp, require_proxy_headers: bool) -> None:
        super().__init__(app)
        self._enabled = require_proxy_headers

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        if self._enabled and not request.headers.get("x-forwarded-proto"):
            self._maybe_warn(request)
        return await call_next(request)

    def _maybe_warn(self, request: Request) -> None:
        now = time.monotonic()
        # Bucket on the path so a flood to one endpoint doesn't silence
        # warnings from a different misconfigured endpoint.
        key = request.url.path
        last = _LAST_WARN_AT.get(key, 0.0)
        if now - last < _WARN_INTERVAL_S:
            return
        _LAST_WARN_AT[key] = now
        client = request.client.host if request.client else "unknown"
        logger.warning(
            "request without X-Forwarded-Proto: path=%s client=%s "
            "(REQUIRE_PROXY_HEADERS is on; cookie Secure flag may be wrong)",
            request.url.path,
            client,
        )
