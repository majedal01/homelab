"""Tests for the YNAB API client, with httpx interactions mocked via respx."""
import httpx
import pytest
import respx

from app.services.ynab_client import DEFAULT_BASE_URL, YNABClient


@respx.mock
async def test_list_budgets_parses_response() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/budgets").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "budgets": [
                        {
                            "id": "b-1",
                            "name": "My Budget",
                            "currency_format": {"iso_code": "USD"},
                            "last_modified_on": "2026-05-15T12:00:00+00:00",
                        }
                    ]
                }
            },
        )
    )
    async with YNABClient("test-token") as client:
        budgets = await client.list_budgets()
    assert len(budgets) == 1
    assert budgets[0].id == "b-1"
    assert budgets[0].name == "My Budget"


@respx.mock
async def test_list_transactions_parses_response() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/budgets/b-1/transactions").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "transactions": [
                        {
                            "id": "t-1",
                            "account_id": "a-1",
                            "category_id": "c-1",
                            "payee_id": "p-1",
                            "date": "2026-05-01",
                            "amount": -25000,
                            "memo": "coffee",
                            "cleared": "cleared",
                            "approved": True,
                        }
                    ]
                }
            },
        )
    )
    async with YNABClient("test-token") as client:
        txns = await client.list_transactions("b-1")
    assert len(txns) == 1
    assert txns[0].amount == -25000


@respx.mock
async def test_rate_limit_header_parsed() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/budgets").mock(
        return_value=httpx.Response(
            200,
            headers={"X-Rate-Limit": "42/200"},
            json={"data": {"budgets": []}},
        )
    )
    async with YNABClient("test-token") as client:
        await client.list_budgets()
        assert client.rate_limit.used == 42
        assert client.rate_limit.limit == 200
        assert client.rate_limit.remaining == 158


async def test_client_requires_context_manager() -> None:
    client = YNABClient("test-token")
    with pytest.raises(RuntimeError, match="async context manager"):
        await client.list_budgets()
