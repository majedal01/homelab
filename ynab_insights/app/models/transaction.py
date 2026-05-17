from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.budget import Budget
    from app.models.category import Category
    from app.models.payee import Payee


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    budget_id: Mapped[str] = mapped_column(ForeignKey("budgets.id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False, index=True)
    category_id: Mapped[str | None] = mapped_column(
        ForeignKey("categories.id"), nullable=True, index=True
    )
    payee_id: Mapped[str | None] = mapped_column(ForeignKey("payees.id"), nullable=True, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    memo: Mapped[str | None] = mapped_column(String, nullable=True)
    cleared: Mapped[str] = mapped_column(String, nullable=False, default="uncleared")
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    budget: Mapped["Budget"] = relationship(back_populates="transactions")
    account: Mapped["Account"] = relationship(back_populates="transactions")
    category: Mapped["Category | None"] = relationship(back_populates="transactions")
    payee: Mapped["Payee | None"] = relationship(back_populates="transactions")
