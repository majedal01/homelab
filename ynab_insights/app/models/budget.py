from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.account import Account
    from app.models.category import Category
    from app.models.payee import Payee
    from app.models.transaction import Transaction


class Budget(Base):
    __tablename__ = "budgets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    last_modified_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    accounts: Mapped[list["Account"]] = relationship(back_populates="budget")
    categories: Mapped[list["Category"]] = relationship(back_populates="budget")
    payees: Mapped[list["Payee"]] = relationship(back_populates="budget")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="budget")
