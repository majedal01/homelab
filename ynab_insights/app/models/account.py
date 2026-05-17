from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.budget import Budget
    from app.models.transaction import Transaction


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    budget_id: Mapped[str] = mapped_column(ForeignKey("budgets.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[str] = mapped_column(String, nullable=False)
    balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    on_budget: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    budget: Mapped["Budget"] = relationship(back_populates="accounts")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")
