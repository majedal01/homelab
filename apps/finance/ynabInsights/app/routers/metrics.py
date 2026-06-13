"""Prometheus scrape endpoint, gated by X-Admin-Token.

Returns 404 (not 401) when the token is wrong or the env var is unset.
Indistinguishable from a non-existent endpoint to scanners; same shape
either way so a misconfigured token doesn't leak that this URL exists.
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from app.config import Settings, get_settings
from app.observability import CONTENT_TYPE_LATEST, REGISTRY, generate_latest

router = APIRouter()

SettingsDep = Annotated[Settings, Depends(get_settings)]


@router.get("/metrics")
async def metrics_endpoint(
    settings: SettingsDep,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> Response:
    expected = settings.metrics_admin_token
    if not expected:
        # Endpoint is effectively disabled when the env var is unset.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if x_admin_token is None or not secrets.compare_digest(x_admin_token, expected):
        # Same response shape regardless of why auth failed: scanners that
        # poke /metrics get a 404 either way.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)

    body = generate_latest(REGISTRY)
    return Response(content=body, media_type=CONTENT_TYPE_LATEST)
