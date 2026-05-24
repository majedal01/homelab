"""Session router: validation, cookie handling, error codes.

The upstream Anthropic ping and YNAB list are monkeypatched in each test
so we never make real network calls.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.session.store import COOKIE_NAME

VALID_YNAB = "a" * 64
VALID_KEY = "sk-ant-" + "a" * 32


@pytest.fixture(autouse=True)
def patch_upstreams(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make _ping_anthropic and _fetch_ynab_budgets succeed without network."""
    from app.routers import session as session_router

    async def fake_ping(key: str) -> None:
        return None

    async def fake_budgets(token: str) -> list[session_router.BudgetOption]:
        return [
            session_router.BudgetOption(id="b-1", name="Main", last_modified_on=datetime.now(UTC)),
            session_router.BudgetOption(id="b-2", name="Side", last_modified_on=datetime.now(UTC)),
        ]

    monkeypatch.setattr(session_router, "_ping_anthropic", fake_ping)
    monkeypatch.setattr(session_router, "_fetch_ynab_budgets", fake_budgets)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    # Reuse the lru_cache'd SessionStore singleton across tests. Calling
    # `get_session_store.cache_clear()` here would create a NEW store on
    # the next router request, but SessionMiddleware was constructed at
    # module-import time with a reference to the ORIGINAL store. The two
    # would diverge: POST /api/session would store the session in the
    # new store, the middleware would look up cookies in the old one,
    # and every subsequent request 401s. Test isolation comes from
    # using a fresh AsyncClient per test (cookies don't leak) and from
    # the random UUID4 sids each session gets.
    from app.main import app

    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as ac:
            yield ac


async def test_create_session_happy_path(client: AsyncClient) -> None:
    r = await client.post(
        "/api/session",
        json={"ynab_token": VALID_YNAB, "anthropic_key": VALID_KEY},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert {"sid", "budgets", "created_at", "expires_at"} <= body.keys()
    assert [b["id"] for b in body["budgets"]] == ["b-1", "b-2"]
    assert COOKIE_NAME in r.cookies
    # Tokens never appear in the response.
    text = r.text
    assert VALID_YNAB not in text
    assert VALID_KEY not in text


async def test_create_session_rejects_bad_ynab_format(client: AsyncClient) -> None:
    r = await client.post(
        "/api/session",
        json={"ynab_token": "short", "anthropic_key": VALID_KEY},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_ynab_token_format"


async def test_create_session_rejects_bad_anthropic_format(client: AsyncClient) -> None:
    r = await client.post(
        "/api/session",
        json={"ynab_token": VALID_YNAB, "anthropic_key": "no-prefix-here"},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["error"] == "invalid_anthropic_key_format"


async def test_create_session_propagates_anthropic_failure(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fastapi import HTTPException

    from app.routers import session as session_router

    async def fail(_key: str) -> None:
        raise HTTPException(
            status_code=401,
            detail={"error": "invalid_anthropic_key", "message": "bad"},
        )

    monkeypatch.setattr(session_router, "_ping_anthropic", fail)

    r = await client.post(
        "/api/session",
        json={"ynab_token": VALID_YNAB, "anthropic_key": VALID_KEY},
    )
    assert r.status_code == 401
    assert r.json()["detail"]["error"] == "invalid_anthropic_key"


async def test_get_session_requires_cookie(client: AsyncClient) -> None:
    r = await client.get("/api/session")
    assert r.status_code == 401
    assert r.json()["detail"] == "session_required"


async def test_get_session_returns_no_tokens(client: AsyncClient) -> None:
    create = await client.post(
        "/api/session",
        json={"ynab_token": VALID_YNAB, "anthropic_key": VALID_KEY},
    )
    assert create.status_code == 200
    r = await client.get("/api/session")
    assert r.status_code == 200
    body = r.json()
    assert "ynab_token" not in body
    assert "anthropic_key" not in body
    assert body["sid"] == create.json()["sid"]


async def test_select_budget_persists_choice(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The /budget endpoint calls two things that hit YNAB: a re-list of
    # budgets to verify the choice is still valid, and fetch_snapshot to
    # pull the full snapshot. Patch both. The list_budgets path goes
    # through `session_router.YNABClient`; the snapshot path goes through
    # the function imported into the session router as `fetch_snapshot`.
    from datetime import UTC, datetime

    from app.routers import session as session_router
    from app.snapshot.models import YnabSnapshot

    class FakeBudget:
        def __init__(self, bid: str, name: str) -> None:
            self.id = bid
            self.name = name

    class FakeClient:
        def __init__(self, token: str) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def list_budgets(self) -> list[FakeBudget]:
            return [FakeBudget("b-1", "Main"), FakeBudget("b-2", "Side")]

    async def fake_fetch_snapshot(token: str, budget_id: str) -> YnabSnapshot:
        return YnabSnapshot(
            budget_id=budget_id,
            budget_name="Side" if budget_id == "b-2" else "Main",
            currency_iso="USD",
            fetched_at=datetime.now(UTC),
            accounts=[],
            categories=[],
            payees=[],
            transactions=[],
        )

    monkeypatch.setattr(session_router, "YNABClient", FakeClient)
    monkeypatch.setattr(session_router, "fetch_snapshot", fake_fetch_snapshot)

    await client.post(
        "/api/session",
        json={"ynab_token": VALID_YNAB, "anthropic_key": VALID_KEY},
    )
    r = await client.post("/api/session/budget", json={"budget_id": "b-2"})
    assert r.status_code == 200, r.text
    assert r.json()["budget_id"] == "b-2"
    assert r.json()["budget_name"] == "Side"


async def test_select_budget_rejects_unknown(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.routers import session as session_router

    class FakeClient:
        def __init__(self, token: str) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def list_budgets(self) -> list[object]:
            return []

    monkeypatch.setattr(session_router, "YNABClient", FakeClient)

    await client.post(
        "/api/session",
        json={"ynab_token": VALID_YNAB, "anthropic_key": VALID_KEY},
    )
    r = await client.post("/api/session/budget", json={"budget_id": "no-such"})
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "budget_not_found"


async def test_delete_session_clears_cookie_and_evicts(client: AsyncClient) -> None:
    create = await client.post(
        "/api/session",
        json={"ynab_token": VALID_YNAB, "anthropic_key": VALID_KEY},
    )
    assert create.status_code == 200
    r = await client.delete("/api/session")
    assert r.status_code == 204
    # Cookie should be cleared (max-age=0 set-cookie); subsequent GET 401s.
    r2 = await client.get("/api/session")
    assert r2.status_code == 401


async def test_refresh_session_requires_budget(client: AsyncClient) -> None:
    await client.post(
        "/api/session",
        json={"ynab_token": VALID_YNAB, "anthropic_key": VALID_KEY},
    )
    r = await client.post("/api/session/refresh")
    assert r.status_code == 409
    assert r.json()["detail"]["error"] == "no_budget_selected"
