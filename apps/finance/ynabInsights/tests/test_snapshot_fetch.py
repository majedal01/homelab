"""fetch_snapshot end-to-end: assembles a YnabSnapshot from mocked YNAB
responses, handles split transactions, drops stale FK references, and
converts milliunits to cents."""

from __future__ import annotations

from typing import Any

import httpx
import pytest
import respx

from app.services.ynab_client import DEFAULT_BASE_URL, fetch_snapshot

BUDGETS: dict[str, Any] = {
    "data": {
        "budgets": [
            {
                "id": "b-1",
                "name": "My Budget",
                "currency_format": {"iso_code": "USD"},
                "last_modified_on": "2026-05-15T12:00:00+00:00",
            },
            {
                "id": "b-2",
                "name": "Side",
                "currency_format": {"iso_code": "USD"},
                "last_modified_on": "2026-05-15T12:00:00+00:00",
            },
        ]
    }
}


def _accounts() -> dict[str, Any]:
    return {
        "data": {
            "accounts": [
                {
                    "id": "a-1",
                    "name": "Checking",
                    "type": "checking",
                    "balance": 1_234_560,  # milliunits -> 123456 cents
                    "on_budget": True,
                    "closed": False,
                },
            ]
        }
    }


def _categories() -> dict[str, Any]:
    return {
        "data": {
            "category_groups": [
                {
                    "categories": [
                        {
                            "id": "c-1",
                            "category_group_id": "g-1",
                            "name": "Groceries",
                            "hidden": False,
                            "goal_type": "TB",
                            "goal_target": 250_000,  # -> 25000 cents
                            "goal_overall_left": 100_000,  # -> 10000 cents
                            "goal_percentage_complete": 60,
                            "goal_months_to_budget": 2,
                        },
                    ]
                }
            ]
        }
    }


def _payees() -> dict[str, Any]:
    return {"data": {"payees": [{"id": "p-1", "name": "Whole Foods"}]}}


def _transactions(amount_milli: int = -25_000) -> dict[str, Any]:
    return {
        "data": {
            "transactions": [
                {
                    "id": "t-1",
                    "account_id": "a-1",
                    "category_id": "c-1",
                    "payee_id": "p-1",
                    "date": "2026-05-01",
                    "amount": amount_milli,
                    "memo": "weekly shop",
                    "cleared": "cleared",
                    "approved": True,
                }
            ]
        }
    }


def _route(path: str, payload: dict[str, Any]) -> None:
    respx.get(f"{DEFAULT_BASE_URL}{path}").mock(return_value=httpx.Response(200, json=payload))


@respx.mock
async def test_fetch_snapshot_builds_full_snapshot() -> None:
    _route("/budgets", BUDGETS)
    _route("/budgets/b-1/accounts", _accounts())
    _route("/budgets/b-1/categories", _categories())
    _route("/budgets/b-1/payees", _payees())
    _route("/budgets/b-1/transactions", _transactions())

    snap = await fetch_snapshot("test-token", "b-1")

    assert snap.budget_id == "b-1"
    assert snap.budget_name == "My Budget"
    assert snap.currency_iso == "USD"
    assert len(snap.accounts) == 1
    assert snap.accounts[0].balance_cents == 123_456  # milliunits / 10
    assert len(snap.categories) == 1
    assert snap.categories[0].goal_target_cents == 25_000
    assert snap.categories[0].goal_overall_left_cents == 10_000
    assert len(snap.transactions) == 1
    assert snap.transactions[0].amount_cents == -2500  # 25k milliunits / 10
    assert snap.transactions[0].category_id == "c-1"


@respx.mock
async def test_fetch_snapshot_raises_when_budget_not_on_account() -> None:
    _route("/budgets", BUDGETS)
    with pytest.raises(ValueError, match="budget"):
        await fetch_snapshot("test-token", "b-does-not-exist")


@respx.mock
async def test_fetch_snapshot_flattens_splits() -> None:
    _route("/budgets", BUDGETS)
    _route("/budgets/b-1/accounts", _accounts())
    _route("/budgets/b-1/categories", _categories())
    _route("/budgets/b-1/payees", _payees())
    _route(
        "/budgets/b-1/transactions",
        {
            "data": {
                "transactions": [
                    {
                        "id": "parent-1",
                        "account_id": "a-1",
                        "category_id": None,  # parent of a split
                        "payee_id": "p-1",
                        "date": "2026-05-02",
                        "amount": -30_000,
                        "cleared": "cleared",
                        "approved": True,
                        "subtransactions": [
                            {
                                "id": "sub-1",
                                "transaction_id": "parent-1",
                                "category_id": "c-1",
                                "payee_id": "p-1",
                                "amount": -20_000,
                                "memo": "produce",
                            },
                            {
                                "id": "sub-2",
                                "transaction_id": "parent-1",
                                "category_id": "c-1",
                                "payee_id": "p-1",
                                "amount": -10_000,
                                "memo": "dairy",
                            },
                        ],
                    }
                ]
            }
        },
    )

    snap = await fetch_snapshot("test-token", "b-1")
    # Parent is NOT surfaced; two legs are.
    ids = {t.id for t in snap.transactions}
    assert ids == {"sub-1", "sub-2"}
    assert all(t.account_id == "a-1" for t in snap.transactions)
    assert all(t.date.isoformat() == "2026-05-02" for t in snap.transactions)


@respx.mock
async def test_fetch_snapshot_nullifies_stale_fk_references() -> None:
    _route("/budgets", BUDGETS)
    _route("/budgets/b-1/accounts", _accounts())
    _route("/budgets/b-1/categories", _categories())
    _route("/budgets/b-1/payees", _payees())
    _route(
        "/budgets/b-1/transactions",
        {
            "data": {
                "transactions": [
                    {
                        "id": "t-1",
                        "account_id": "a-1",
                        "category_id": "c-gone",  # not in /categories
                        "payee_id": "p-gone",  # not in /payees
                        "date": "2026-05-01",
                        "amount": -1000,
                        "cleared": "cleared",
                        "approved": True,
                    }
                ]
            }
        },
    )
    snap = await fetch_snapshot("test-token", "b-1")
    assert snap.transactions[0].category_id is None
    assert snap.transactions[0].payee_id is None


@respx.mock
async def test_fetch_snapshot_sorts_transactions_newest_first() -> None:
    _route("/budgets", BUDGETS)
    _route("/budgets/b-1/accounts", _accounts())
    _route("/budgets/b-1/categories", _categories())
    _route("/budgets/b-1/payees", _payees())
    _route(
        "/budgets/b-1/transactions",
        {
            "data": {
                "transactions": [
                    {
                        "id": "old",
                        "account_id": "a-1",
                        "category_id": "c-1",
                        "payee_id": "p-1",
                        "date": "2026-01-01",
                        "amount": -100,
                        "cleared": "cleared",
                        "approved": True,
                    },
                    {
                        "id": "new",
                        "account_id": "a-1",
                        "category_id": "c-1",
                        "payee_id": "p-1",
                        "date": "2026-05-01",
                        "amount": -100,
                        "cleared": "cleared",
                        "approved": True,
                    },
                ]
            }
        },
    )
    snap = await fetch_snapshot("test-token", "b-1")
    assert [t.id for t in snap.transactions] == ["new", "old"]
