"""Session store: TTL eviction, signing, absolute-cap enforcement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

# Module-level imports of the FastAPI symbols used by the middleware tests
# below. `from __future__ import annotations` turns parameter types into
# strings, so FastAPI resolves them via `get_type_hints(func, globalns)`.
# That resolver only sees the function's __globals__; if `Request` or
# `CurrentSessionDep` were imported inside the test function, get_type_hints
# would NameError, and FastAPI would silently fall back to treating the
# parameter as a Pydantic body and return 422.
from app.session.middleware import CurrentSessionDep, SessionMiddleware
from app.session.models import UserSession
from app.session.store import SessionStore, new_sid


def _make_session(sid: str | None = None) -> UserSession:
    return UserSession(
        sid=sid or new_sid(),
        ynab_token=SecretStr("0" * 64),
        anthropic_key=SecretStr("sk-ant-test"),
    )


def test_create_and_get_round_trip() -> None:
    store = SessionStore(secret_key="test")
    s = _make_session()
    store.create(s)
    assert store.get(s.sid) is s


def test_get_unknown_returns_none() -> None:
    store = SessionStore(secret_key="test")
    assert store.get("nope") is None


def test_evict_drops_session() -> None:
    store = SessionStore(secret_key="test")
    s = _make_session()
    store.create(s)
    store.evict(s.sid)
    assert store.get(s.sid) is None


def test_get_extends_idle_ttl_window() -> None:
    # Tiny TTL so we can observe; insertion timestamp is what TTLCache pins.
    store = SessionStore(secret_key="test", idle_ttl_seconds=10)
    s = _make_session()
    store.create(s)
    # Re-reading should re-insert and bump TTL; observable via last_active_at.
    before = s.last_active_at
    s.last_active_at = before - timedelta(seconds=5)
    got = store.get(s.sid)
    assert got is not None
    assert got.last_active_at > before - timedelta(seconds=5)


def test_absolute_cap_evicts_old_session() -> None:
    store = SessionStore(secret_key="test", absolute_ttl_seconds=1)
    s = _make_session()
    s.created_at = datetime.now(UTC) - timedelta(seconds=10)
    store.create(s)
    assert store.get(s.sid) is None
    # Cache entry is gone after the get-side eviction.
    assert store.get(s.sid) is None


def test_maxsize_lru_evicts_oldest() -> None:
    store = SessionStore(secret_key="test", maxsize=2)
    a, b, c = _make_session("a"), _make_session("b"), _make_session("c")
    store.create(a)
    store.create(b)
    store.create(c)  # forces eviction of `a`
    assert store.get("a") is None
    assert store.get("b") is not None
    assert store.get("c") is not None


def test_sign_and_unsign_round_trip() -> None:
    store = SessionStore(secret_key="test")
    sid = new_sid()
    signed = store.sign(sid)
    assert store.unsign(signed) == sid


def test_unsign_rejects_tampered_cookie() -> None:
    store = SessionStore(secret_key="test")
    signed = store.sign(new_sid())
    tampered = signed[:-2] + ("xx" if not signed.endswith("xx") else "yy")
    assert store.unsign(tampered) is None


def test_unsign_rejects_wrong_secret() -> None:
    a = SessionStore(secret_key="alpha")
    b = SessionStore(secret_key="beta")
    assert b.unsign(a.sign(new_sid())) is None


def test_expires_at_uses_smaller_of_idle_or_absolute() -> None:
    store = SessionStore(secret_key="test", idle_ttl_seconds=3600, absolute_ttl_seconds=14400)
    s = _make_session()
    # Fresh session: idle cap < absolute cap.
    assert store.expires_at(s) == s.last_active_at + timedelta(seconds=3600)

    # Aged session: absolute cap may bite first.
    s.created_at = datetime.now(UTC) - timedelta(hours=4)
    expected = s.created_at + timedelta(seconds=14400)
    assert store.expires_at(s) == expected


def test_new_sid_is_unique_and_long_enough() -> None:
    a, b = new_sid(), new_sid()
    assert a != b
    assert len(a) >= 32


def test_user_session_redacts_tokens_in_repr() -> None:
    s = _make_session()
    text = repr(s)
    assert "test" not in text  # secret value
    assert "SecretStr" in text or "**********" in text


@pytest.mark.asyncio
async def test_middleware_resolves_signed_cookie_to_session() -> None:
    """Round-trip: middleware should attach the session to request.state."""
    store = SessionStore(secret_key="test")
    s = _make_session()
    store.create(s)

    app = FastAPI()
    app.add_middleware(SessionMiddleware, store=store)

    @app.get("/peek")
    async def peek(request: Request) -> dict[str, str | None]:
        sess = getattr(request.state, "session", None)
        return {"sid": sess.sid if sess else None}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        cookies={"sid": store.sign(s.sid)},
    ) as client:
        r = await client.get("/peek")
        assert r.status_code == 200
        assert r.json() == {"sid": s.sid}


@pytest.mark.asyncio
async def test_middleware_no_cookie_leaves_session_none() -> None:
    store = SessionStore(secret_key="test")
    app = FastAPI()
    app.add_middleware(SessionMiddleware, store=store)

    @app.get("/peek")
    async def peek(request: Request) -> dict[str, bool]:
        return {"has_session": getattr(request.state, "session", None) is not None}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/peek")
        assert r.status_code == 200
        assert r.json() == {"has_session": False}


@pytest.mark.asyncio
async def test_current_session_dep_401s_without_cookie() -> None:
    store = SessionStore(secret_key="test")
    app = FastAPI()
    app.add_middleware(SessionMiddleware, store=store)

    @app.get("/protected")
    async def protected(session: CurrentSessionDep) -> dict[str, str]:
        assert isinstance(session, UserSession)
        return {"sid": session.sid}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        r = await client.get("/protected")
        assert r.status_code == 401
        assert r.json()["detail"] == "session_required"
