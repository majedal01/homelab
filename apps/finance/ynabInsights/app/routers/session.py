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

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, SecretStr

from app.demo import build_demo_insights, build_demo_snapshot
from app.llm import (
    ALLOWED_MODELS,
    DEFAULT_MODEL_FOR_PROVIDER,
    MODEL_CATALOG,
    InvalidApiKeyError,
    ProviderBillingError,
    ProviderUnavailableError,
    build_provider,
    detect_provider,
)
from app.observability import metrics
from app.services.ynab_client import YNABClient, fetch_snapshot
from app.session.middleware import CurrentSessionDep
from app.session.models import SessionPublic, UserSession
from app.session.store import COOKIE_NAME, SessionStore, get_session_store, new_sid

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/session", tags=["session"])

# Cheap format gate before any network call.
YNAB_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{20,128}$")


StoreDep = Annotated[SessionStore, Depends(get_session_store)]


class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ynab_token: SecretStr
    # Backwards-compat alias: pre-v2.6d clients still send `anthropic_key`.
    # New v2.6d clients send `llm_key` which can be Anthropic OR OpenAI.
    llm_key: SecretStr | None = None
    anthropic_key: SecretStr | None = None
    # Optional. Server validates against ALLOWED_MODELS[provider]. When
    # omitted, the session falls through to DEFAULT_MODEL_FOR_PROVIDER.
    anthropic_model: str | None = None


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


class ModelOptionResponse(BaseModel):
    value: str
    label: str
    tagline: str


class ModelCatalogResponse(BaseModel):
    """Public per-provider model catalog for the sign-in picker."""

    providers: dict[str, list[ModelOptionResponse]]
    defaults: dict[str, str]


def _bad(code: str, message: str, http_status: int = status.HTTP_400_BAD_REQUEST) -> HTTPException:
    return HTTPException(status_code=http_status, detail={"error": code, "message": message})


async def _ping_provider(key: SecretStr, provider_name: str) -> None:
    """Validate the key by hitting the provider's cheapest endpoint.

    Raises HTTPException with a specific error code on failure. Per-provider
    failure mapping happens inside the provider SDK; this just translates
    `LlmProviderError` subclasses into our session-router error taxonomy.
    """

    inferred = detect_provider(key.get_secret_value())
    if inferred is None:
        metrics.provider_validation_failures_total.labels(
            provider="n/a", error_code="unknown_provider"
        ).inc()
        raise _bad("unknown_provider", "That key didn't match a known provider.", 400)
    llm = build_provider(inferred, key, DEFAULT_MODEL_FOR_PROVIDER[inferred])
    try:
        await llm.ping()
    except InvalidApiKeyError as e:
        metrics.provider_validation_failures_total.labels(
            provider=inferred, error_code="invalid_key"
        ).inc()
        raise _bad(
            f"invalid_{provider_name}_key",
            f"That {provider_name.title()} key was rejected.",
            401,
        ) from e
    except ProviderBillingError as e:
        metrics.provider_validation_failures_total.labels(
            provider=inferred, error_code="billing"
        ).inc()
        raise _bad(
            f"{provider_name}_billing",
            f"{provider_name.title()} returned a billing or permission error.",
            402,
        ) from e
    except ProviderUnavailableError as e:
        metrics.provider_validation_failures_total.labels(
            provider=inferred, error_code="unavailable"
        ).inc()
        raise _bad(
            f"{provider_name}_unavailable",
            f"Couldn't reach {provider_name.title()}. Try again in a moment.",
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
        BudgetOption(id=b.id, name=b.name, last_modified_on=b.last_modified_on) for b in budgets
    ]


@router.get("/models", response_model=ModelCatalogResponse)
async def list_models() -> ModelCatalogResponse:
    """Public LLM model catalog for the sign-in picker (no session required).

    The single source of truth is `app/llm` — the picker renders whatever this
    returns, so the model list never drifts from the server's allow-list.
    """
    return ModelCatalogResponse(
        providers={
            provider: [
                ModelOptionResponse(value=o.value, label=o.label, tagline=o.tagline)
                for o in options
            ]
            for provider, options in MODEL_CATALOG.items()
        },
        defaults={str(provider): model for provider, model in DEFAULT_MODEL_FOR_PROVIDER.items()},
    )


@router.post("", response_model=CreateSessionResponse)
async def create_session(
    body: CreateSessionRequest,
    request: Request,
    response: Response,
    store: StoreDep,
) -> CreateSessionResponse:
    """Validate both keys, fetch budgets, mint a session, set the cookie."""
    ynab_token = body.ynab_token.get_secret_value()
    # Accept either field for the LLM key. New v2.6d clients send `llm_key`;
    # older clients still send `anthropic_key`. Same SecretStr type either way.
    llm_key_secret = body.llm_key or body.anthropic_key
    if llm_key_secret is None:
        raise _bad("missing_llm_key", "An Anthropic or OpenAI key is required.")
    llm_key = llm_key_secret.get_secret_value()

    if not YNAB_TOKEN_RE.match(ynab_token):
        raise _bad("invalid_ynab_token_format", "YNAB token format looks wrong.")

    provider = detect_provider(llm_key)
    if provider is None:
        raise _bad(
            "unknown_provider",
            "That key didn't match a known provider. Expected sk-ant-… or sk-…",
        )
    if body.anthropic_model is not None and body.anthropic_model not in ALLOWED_MODELS[provider]:
        raise _bad(
            "unknown_model",
            f"That model isn't supported for {provider}. "
            f"Pick one of: {', '.join(sorted(ALLOWED_MODELS[provider]))}.",
        )

    await _ping_provider(llm_key_secret, provider)
    budgets = await _fetch_ynab_budgets(ynab_token)

    session = UserSession(
        sid=new_sid(),
        ynab_token=SecretStr(ynab_token),
        anthropic_key=llm_key_secret,
        anthropic_model=body.anthropic_model,
    )
    store.create(session)
    metrics.sessions_created_total.labels(is_demo="false", provider=provider).inc()

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


@router.post("/demo", response_model=SessionPublic)
async def create_demo_session(
    request: Request,
    response: Response,
    store: StoreDep,
) -> SessionPublic:
    """Mint a demo session with pre-loaded sample data. No tokens, no
    upstream calls, no LLM cost. The visitor lands on a populated feed
    and can explore Insights + Explore. Ask is disabled in demo mode."""
    snapshot = build_demo_snapshot()
    insights = build_demo_insights(snapshot)
    session = UserSession(
        sid=new_sid(),
        # SecretStr requires a value; empty string is fine because the demo
        # code path never reads it (is_demo gates every LLM/YNAB call site).
        ynab_token=SecretStr(""),
        anthropic_key=SecretStr(""),
        is_demo=True,
        budget_id=snapshot.budget_id,
        budget_name=snapshot.budget_name,
        snapshot=snapshot,
        insights=insights,
        last_synced_at=snapshot.fetched_at,
    )
    store.create(session)
    metrics.sessions_created_total.labels(is_demo="true", provider="n/a").inc()
    metrics.demo_session_active.inc()

    response.set_cookie(
        key=COOKIE_NAME,
        value=store.sign(session.sid),
        max_age=store.cookie_max_age,
        httponly=True,
        secure=_should_use_secure_cookie(request),
        samesite="strict",
        path="/",
    )
    return _to_public(session, store)


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

    try:
        snapshot = await fetch_snapshot(token, match.id)
    except httpx.HTTPError as e:
        logger.info("snapshot fetch failed: %s", type(e).__name__)
        raise _bad("ynab_unavailable", "Couldn't pull your budget. Try again.", 502) from e

    session.budget_id = match.id
    session.budget_name = match.name
    session.snapshot = snapshot
    session.last_synced_at = datetime.now(UTC)
    # Insights from the prior budget are no longer relevant; clear them so the
    # feed reflects the new scope on next /api/insights call.
    session.insights = []
    return _to_public(session, store)


@router.get("", response_model=SessionPublic)
async def get_session(session: CurrentSessionDep, store: StoreDep) -> SessionPublic:
    return _to_public(session, store)


@router.post("/refresh", response_model=SessionPublic)
async def refresh_session(session: CurrentSessionDep, store: StoreDep) -> SessionPublic:
    """Re-fetch the YNAB snapshot for the active budget."""
    if session.is_demo:
        # Refresh would call YNAB with empty tokens. Just bump last_active.
        session.last_active_at = datetime.now(UTC)
        return _to_public(session, store)
    if session.budget_id is None:
        raise _bad("no_budget_selected", "Pick a budget before refreshing.", 409)
    try:
        snapshot = await fetch_snapshot(
            session.ynab_token.get_secret_value(),
            session.budget_id,
        )
    except httpx.HTTPError as e:
        logger.info("snapshot refresh failed: %s", type(e).__name__)
        raise _bad("ynab_unavailable", "Couldn't reach YNAB. Try again.", 502) from e
    session.snapshot = snapshot
    session.last_synced_at = datetime.now(UTC)
    # Invalidate cached insights so the next /api/insights call regenerates
    # against the new data.
    session.insights = []
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
        anthropic_model=session.anthropic_model,
        is_demo=session.is_demo,
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
