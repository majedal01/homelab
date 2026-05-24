"""ASGI middleware that resolves the session cookie into `request.state.session`.

Authenticated routers depend on `current_session` (FastAPI dep) which reads
`request.state.session` and 401s if missing. Unauthenticated routes (the
session-create endpoint, /health, /welcome) ignore the absence.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
from starlette.types import ASGIApp

from app.session.models import UserSession
from app.session.store import COOKIE_NAME, SessionStore

logger = logging.getLogger(__name__)


class SessionMiddleware(BaseHTTPMiddleware):
    """Reads the signed `sid` cookie, looks up the session, attaches it.

    Always runs; never rejects. Endpoints that require a session declare
    `current_session` as a dependency and 401 themselves. This keeps the
    public surface (welcome, health, session-create) free of middleware
    branching logic.
    """

    def __init__(self, app: ASGIApp, store: SessionStore) -> None:
        super().__init__(app)
        self._store = store

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.session = None
        signed = request.cookies.get(COOKIE_NAME)
        if signed:
            sid = self._store.unsign(signed)
            if sid:
                session = self._store.get(sid)
                if session is not None:
                    request.state.session = session
        return await call_next(request)


def current_session(request: Request) -> UserSession:
    """FastAPI dependency: 401 unless a valid session is on the request."""
    session: UserSession | None = getattr(request.state, "session", None)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="session_required",
        )
    return session


CurrentSessionDep = Annotated[UserSession, Depends(current_session)]
