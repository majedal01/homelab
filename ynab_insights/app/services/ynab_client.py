"""Async client for the YNAB REST API.

Wraps GET endpoints for budgets, accounts, categories, payees, and transactions.
Responses are parsed into Pydantic models that mirror only the fields we persist.
Transient errors are retried with exponential backoff. Rate-limit headers are
tracked so the caller can back off near the YNAB ceiling (200 req/hr per token).
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from types import TracebackType
from typing import Any

import httpx
from pydantic import BaseModel
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.ynab.com/v1"


class YNABBudget(BaseModel):
    id: str
    name: str
    currency_format: dict[str, Any] | None = None
    last_modified_on: datetime


class YNABAccount(BaseModel):
    id: str
    name: str
    type: str
    balance: int  # YNAB milliunits
    on_budget: bool
    closed: bool


class YNABCategory(BaseModel):
    id: str
    category_group_id: str | None = None
    name: str
    hidden: bool = False


class YNABPayee(BaseModel):
    id: str
    name: str
    transfer_account_id: str | None = None


class YNABTransaction(BaseModel):
    id: str
    account_id: str
    category_id: str | None = None
    payee_id: str | None = None
    date: date
    amount: int  # YNAB milliunits, can be negative
    memo: str | None = None
    cleared: str = "uncleared"
    approved: bool = False


class RateLimitInfo(BaseModel):
    """Snapshot of YNAB rate-limit headers from the most recent response."""

    used: int = 0
    limit: int = 200
    reset: datetime | None = None

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)


class YNABClient:
    """Async context-managed YNAB client.

    Usage:
        async with YNABClient(token) as client:
            budgets = await client.list_budgets()
    """

    def __init__(
        self,
        token: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._token = token
        self._base_url = base_url
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self.rate_limit = RateLimitInfo()

    async def __aenter__(self) -> YNABClient:
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=self._timeout,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def list_budgets(self) -> list[YNABBudget]:
        payload = await self._get("/budgets")
        return [YNABBudget.model_validate(b) for b in payload["data"]["budgets"]]

    async def list_accounts(self, budget_id: str) -> list[YNABAccount]:
        payload = await self._get(f"/budgets/{budget_id}/accounts")
        return [YNABAccount.model_validate(a) for a in payload["data"]["accounts"]]

    async def list_categories(self, budget_id: str) -> list[YNABCategory]:
        payload = await self._get(f"/budgets/{budget_id}/categories")
        out: list[YNABCategory] = []
        for group in payload["data"]["category_groups"]:
            for cat in group.get("categories", []):
                out.append(YNABCategory.model_validate(cat))
        return out

    async def list_payees(self, budget_id: str) -> list[YNABPayee]:
        payload = await self._get(f"/budgets/{budget_id}/payees")
        return [YNABPayee.model_validate(p) for p in payload["data"]["payees"]]

    async def list_transactions(self, budget_id: str) -> list[YNABTransaction]:
        payload = await self._get(f"/budgets/{budget_id}/transactions")
        return [YNABTransaction.model_validate(t) for t in payload["data"]["transactions"]]

    @retry(
        retry=retry_if_exception_type((httpx.TransportError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        reraise=True,
    )
    async def _get(self, path: str) -> dict[str, Any]:
        if self._client is None:
            raise RuntimeError("YNABClient must be used as an async context manager")
        if self.rate_limit.remaining <= 5:
            logger.warning(
                "approaching YNAB rate limit: %d/%d used",
                self.rate_limit.used,
                self.rate_limit.limit,
            )
        response = await self._client.get(path)
        self._update_rate_limit(response)
        response.raise_for_status()
        result: dict[str, Any] = response.json()
        return result

    def _update_rate_limit(self, response: httpx.Response) -> None:
        # YNAB returns headers like "X-Rate-Limit: 17/200" (used/limit).
        header = response.headers.get("X-Rate-Limit")
        if not header or "/" not in header:
            return
        used_str, limit_str = header.split("/", 1)
        try:
            self.rate_limit = RateLimitInfo(
                used=int(used_str.strip()),
                limit=int(limit_str.strip()),
            )
        except ValueError:
            logger.warning("could not parse X-Rate-Limit header: %r", header)


def milliunits_to_cents(milliunits: int) -> int:
    """Convert YNAB milliunits to cents. YNAB stores amounts at 1/1000 precision;
    cents is 1/100. Integer division by 10 is exact for valid YNAB values."""
    return milliunits // 10
