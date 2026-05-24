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
    # YNAB goal fields. All optional; only present when the user configured a goal
    # on the category. Stored in milliunits where applicable; converted on ingest.
    goal_type: str | None = None
    goal_target: int | None = None  # milliunits
    goal_target_month: date | None = None
    goal_percentage_complete: int | None = None
    goal_overall_left: int | None = None  # milliunits
    goal_months_to_budget: int | None = None


class YNABPayee(BaseModel):
    id: str
    name: str
    transfer_account_id: str | None = None


class YNABSubTransaction(BaseModel):
    """One leg of a split. YNAB returns these inside the parent's
    `subtransactions` array. The sub carries its own category, payee, amount,
    and memo; the parent provides the date and account."""

    id: str
    transaction_id: str  # parent transaction id
    category_id: str | None = None
    payee_id: str | None = None
    amount: int  # milliunits, can be negative
    memo: str | None = None


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
    # Populated for split transactions; the parent's category_id is null and
    # the parent's amount equals the sum of subtransaction amounts.
    subtransactions: list[YNABSubTransaction] = []


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


async def fetch_snapshot(token: str, budget_id: str) -> YnabSnapshot:
    """One full snapshot of one budget. Used by the session layer (v2.5).

    Pulls accounts, categories, payees, and transactions sequentially.
    Splits are flattened into top-level transactions with the parent's
    date and account. References to YNAB entities that no longer exist
    in the current /categories or /payees responses are nulled out so
    the snapshot stays self-consistent.
    """
    from datetime import UTC, datetime

    from app.snapshot.models import (
        Account as SnapAccount,
    )
    from app.snapshot.models import (
        Category as SnapCategory,
    )
    from app.snapshot.models import (
        Payee as SnapPayee,
    )
    from app.snapshot.models import (
        Transaction as SnapTransaction,
    )
    from app.snapshot.models import (
        YnabSnapshot,
    )

    async with YNABClient(token) as client:
        budgets = await client.list_budgets()
        budget = next((b for b in budgets if b.id == budget_id), None)
        if budget is None:
            raise ValueError(f"budget {budget_id!r} not on this account")

        accounts = await client.list_accounts(budget_id)
        categories = await client.list_categories(budget_id)
        payees = await client.list_payees(budget_id)
        transactions = await client.list_transactions(budget_id)

    snap_accounts = [
        SnapAccount(
            id=a.id,
            name=a.name,
            type=a.type,
            on_budget=a.on_budget,
            closed=a.closed,
            balance_cents=milliunits_to_cents(a.balance),
        )
        for a in accounts
    ]
    snap_categories = [
        SnapCategory(
            id=c.id,
            name=c.name,
            category_group_id=c.category_group_id,
            hidden=c.hidden,
            goal_type=c.goal_type,
            goal_target_cents=milliunits_to_cents(c.goal_target) if c.goal_target else None,
            goal_target_month=c.goal_target_month,
            goal_percentage_complete=c.goal_percentage_complete,
            goal_overall_left_cents=(
                milliunits_to_cents(c.goal_overall_left) if c.goal_overall_left else None
            ),
            goal_months_to_budget=c.goal_months_to_budget,
        )
        for c in categories
    ]
    snap_payees = [
        SnapPayee(id=p.id, name=p.name, transfer_account_id=p.transfer_account_id)
        for p in payees
    ]

    known_category_ids = {c.id for c in snap_categories}
    known_payee_ids = {p.id for p in snap_payees}
    snap_transactions: list[SnapTransaction] = []
    for txn in transactions:
        if txn.subtransactions:
            # Split transaction: emit one snapshot row per leg, inheriting the
            # parent's date and account. The parent itself is not surfaced
            # (its amount equals the sum of legs).
            for sub in txn.subtransactions:
                cat_id = sub.category_id if sub.category_id in known_category_ids else None
                payee_id = sub.payee_id if sub.payee_id in known_payee_ids else None
                snap_transactions.append(
                    SnapTransaction(
                        id=sub.id,
                        date=txn.date,
                        amount_cents=milliunits_to_cents(sub.amount),
                        account_id=txn.account_id,
                        payee_id=payee_id,
                        category_id=cat_id,
                        memo=sub.memo,
                    )
                )
        else:
            cat_id = txn.category_id if txn.category_id in known_category_ids else None
            payee_id = txn.payee_id if txn.payee_id in known_payee_ids else None
            snap_transactions.append(
                SnapTransaction(
                    id=txn.id,
                    date=txn.date,
                    amount_cents=milliunits_to_cents(txn.amount),
                    account_id=txn.account_id,
                    payee_id=payee_id,
                    category_id=cat_id,
                    memo=txn.memo,
                )
            )

    # Newest-first sort. Generators assume this ordering for cheap "last N"
    # slices without re-sorting.
    snap_transactions.sort(key=lambda t: (t.date, t.id), reverse=True)

    currency = "USD"
    if budget.currency_format and "iso_code" in budget.currency_format:
        currency = str(budget.currency_format["iso_code"])

    return YnabSnapshot(
        budget_id=budget_id,
        budget_name=budget.name,
        currency_iso=currency,
        fetched_at=datetime.now(UTC),
        accounts=snap_accounts,
        categories=snap_categories,
        payees=snap_payees,
        transactions=snap_transactions,
    )


# Re-exported as a forward ref so module imports stay light.
if False:  # pragma: no cover - type-only
    from app.snapshot.models import YnabSnapshot  # noqa: F401
