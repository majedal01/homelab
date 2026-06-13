"""In-memory data layer that replaces SQLAlchemy in v2.5.

`models.py` holds Pydantic shapes for one budget's YNAB data;
`queries.py` (added in commit 3) holds the pure-Python aggregations
that the generators consume.
"""

from app.snapshot.models import (
    Account,
    Category,
    Payee,
    Transaction,
    YnabSnapshot,
)

__all__ = ["Account", "Category", "Payee", "Transaction", "YnabSnapshot"]
