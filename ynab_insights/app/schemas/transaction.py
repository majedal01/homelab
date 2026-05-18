from datetime import date

from pydantic import BaseModel


class TransactionResponse(BaseModel):
    """Transaction with embedded entity names so the dashboard can render
    a row without follow-up requests. Names are nullable: `category_name`
    and `payee_name` are None when the underlying FK is null (split parents,
    uncategorized transactions). `account_name` is always populated.

    `transfer_account_id` is the destination account when the payee represents
    a transfer; the frontend uses it to exclude transfers from spending rollups.
    """

    id: str
    budget_id: str
    account_id: str
    account_name: str
    category_id: str | None
    category_name: str | None
    payee_id: str | None
    payee_name: str | None
    transfer_account_id: str | None
    date: date
    amount_cents: int
    memo: str | None
    cleared: str
    approved: bool
