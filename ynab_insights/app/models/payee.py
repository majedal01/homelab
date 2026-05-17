from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.budget import Budget
    from app.models.transaction import Transaction


class Payee(Base):
    __tablename__ = "payees"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    budget_id: Mapped[str] = mapped_column(ForeignKey("budgets.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    transfer_account_id: Mapped[str | None] = mapped_column(String, nullable=True)

    budget: Mapped["Budget"] = relationship(back_populates="payees")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="payee")
