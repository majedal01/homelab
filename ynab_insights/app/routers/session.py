"""Session lifecycle: create, read, refresh, delete, pick budget.

Token validation is two upstream pings (Anthropic + YNAB) wrapped in
specific error codes so the frontend can render targeted messages. Tokens
never appear in responses, never get logged.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from typing import Annotated, Literal

import anthropic
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, SecretStr

from app.services.ynab_client import YNABClient
from app.session.middleware import CurrentSessionDep
from app.session.models import SessionPublic, UserSession
from app.session.store import COOKIE_NAME, SessionStore, get_session_store, new_sid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session", tags=["session"])

# Format gates: cheap checks before any network call.
YNAB_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")
ANTHROPIC_KEY_RE = re.compile(r"^sk-ant-[A-Za-z0-9_-]{20,256}$")


StoreDep = Annotated[SessionStore, Depends(get_session_store)]


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ynab_token: SecretStr
    anthropic_key: SecretStr


class BudgetOption(BaseModel):
    id: str
    name: str
    last_modified_on: datetime


class CreateSessionResponse(BaseModel):
    """Returned after the two upstream pings + budget list fetch.

    No tokens. The frontend picks a budget from this list and posts the
    choice back via POST /api/session/budget.
    """

    sid: str
    budgets: list[BudgetOption]
    created_at: datetime
    expires_at: datetime


class SelectBudgetRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    budget_id: str


class SessionErrorBody(BaseModel):
    error: str
    message: str


def _bad(code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"error": code, "message": message})


async def _ping_anthropic(key: str) -> None:
    """Cheapest meaningful liveness check: 1-token messages.create.

    Raises HTTPException with a specific error code on failure.
    """
    client = anthropic.AsyncAnthropic(api_key=key)
    try:
        await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=1,
            messages=[{"role": "user", "content": "ok"}],
        )
    except anthropic.AuthenticationError as e:
        raise _bad("invalid_anthropic_key", "That Anthropic key was rejected.", 401) from e
    except anthropic.PermissionDeniedError as e:
        raise _bad(
            "anthropic_billing",
            "Anthropic returned a billing or permission error.",
            402,
        ) from e
    except anthropic.APIError as e:
        # Hide upstream details from the response; log the type only.
        logger.info("anthropic ping failed: %s", type(e).__name__)
        raise _bad(
            "anthropic_unavailable",
            "Couldn't reach Anthropic. Try again in a moment.",
            502,
        ) from e


async def _fetch_ynab_budgets(token: str) -> list[BudgetOption]:
    """Fetch budgets with the user's token. Specific error codes per failure mode."""
    try:
        async with YNABClient(token) as client:
            budgets = await client.list_budgets()
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            raise _bad("invalid_ynab_token", "That YNAB token was rejected.", 401) from e
        if e.response.status_code == 429:
            retry_after = e.response.headers.get("Retry-After", "60")
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "ynab_rate_limited",
                    "message": "YNAB rate limit hit. Try again shortly.",
                    "retry_after_seconds": int(retry_after) if retry_after.isdigit() else 60,
                },
            ) from e
        logger.info("ynab budgets fetch failed: status=%s", e.response.status_code)
        raise _bad("ynab_unavailable", "Couldn't reach YNAB. Try again in a moment.", 502) from e
    except httpx.HTTPError as e:
        logger.info("ynab transport error: %s", type(e).__name__)
        raise _bad("ynab_unavailable", "Couldn't reach YNAB. Try again in a moment.", 502) from e
    return [
        BudgetOption(id=b.id, name=b.name, last_modified_on=b.last_modified_on)
        for b in budgets
    ]


@router.post("", response_model=CreateSessionResponse)
async def create_session(
    body: CreateSessionRequest,
    request: Request,
    response: Response,
    store: StoreDep,
) -> CreateSessionResponse:
    """Validate both keys, fetch budgets, mint a session, set the cookie."""
    ynab_token = body.ynab_token.get_secret_value()
    anthropic_key = body.anthropic_key.get_secret_value()

    if not YNAB_TOKEN_RE.match(ynab_token):
        raise _bad("invalid_ynab_token_format", "YNAB token format looks wrong.")
    if not ANTHROPIC_KEY_RE.match(anthropic_key):
        raise _bad("invalid_anthropic_key_format", "Anthropic keys start with 'sk-ant-'.")

    await _ping_anthropic(anthropic_key)
    budgets = await _fetch_ynab_budgets(ynab_token)

    session = UserSession(
        sid=new_sid(),
        ynab_token=SecretStr(ynab_token),
        anthropic_key=SecretStr(anthropic_key),
    )
    store.create(session)

    response.set_cookie(
        key=COOKIE_NAME,
        value=store.sign(session.sid),
        max_age=store.cookie_max_age,
        httponly=True,
        secure=_should_use_secure_cookie(request),
        samesite="strict",
        path="/",
    )

    return CreateSessionResponse(
        sid=session.sid,
        budgets=budgets,
        created_at=session.created_at,
        expires_at=store.expires_at(session),
    )


@router.post("/budget", response_model=SessionPublic)
async def select_budget(
    body: SelectBudgetRequest,
    session: CurrentSessionDep,
    store: StoreDep,
) -> SessionPublic:
    """Set the active budget and fetch the snapshot.

    The snapshot fetch itself is added in commit 3; for now we record the
    budget id and name so the frontend can confirm the selection.
    """
    token = session.ynab_token.get_secret_value()
    try:
        async with YNABClient(token) as client:
            budgets = await client.list_budgets()
    except httpx.HTTPError as e:
        logger.info("ynab refetch on budget select failed: %s", type(e).__name__)
        raise _bad("ynab_unavailable", "Couldn't reach YNAB. Try again in a moment.", 502) from e

    match = next((b for b in budgets if b.id == body.budget_id), None)
    if match is None:
        raise _bad("budget_not_found", "That budget is not on this YNAB account.", 404)

    session.budget_id = match.id
    session.budget_name = match.name
    session.last_synced_at = datetime.now(UTC)
    return _to_public(session, store)


@router.get("", response_model=SessionPublic)
async def get_session(session: CurrentSessionDep, store: StoreDep) -> SessionPublic:
    return _to_public(session, store)


@router.post("/refresh", response_model=SessionPublic)
async def refresh_session(session: CurrentSessionDep, store: StoreDep) -> SessionPublic:
    """Re-fetch the YNAB snapshot for the active budget.

    Snapshot fetching wires up in commit 3; for now this bumps last_synced_at
    so the frontend's refresh button has a working endpoint to call.
    """
    if session.budget_id is None:
        raise _bad("no_budget_selected", "Pick a budget before refreshing.", 409)
    session.last_synced_at = datetime.now(UTC)
    return _to_public(session, store)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def delete_session(
    session: CurrentSessionDep, store: StoreDep, response: Response
) -> Response:
    store.evict(session.sid)
    response.delete_cookie(COOKIE_NAME, path="/")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _to_public(session: UserSession, store: SessionStore) -> SessionPublic:
    return SessionPublic(
        sid=session.sid,
        budget_id=session.budget_id,
        budget_name=session.budget_name,
        created_at=session.created_at,
        last_active_at=session.last_active_at,
        last_synced_at=session.last_synced_at,
        expires_at=store.expires_at(session),
    )


def _should_use_secure_cookie(request: Request) -> bool:
    """Set Secure=True except for plain-HTTP localhost dev.

    Behind the prod / stage reverse proxy the request URL scheme is `http`
    even when the client used HTTPS, but the `X-Forwarded-Proto` header
    carries the real scheme. Honor that.
    """
    forwarded = request.headers.get("x-forwarded-proto", "").lower()
    if forwarded == "https":
        return True
    if request.url.scheme == "https":
        return True
    return False


# Typing alias so the literal stays in one place.
SessionStatus = Literal["active", "expired"]
