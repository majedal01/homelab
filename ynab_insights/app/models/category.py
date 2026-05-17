from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.budget import Budget
    from app.models.transaction import Transaction


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    budget_id: Mapped[str] = mapped_column(ForeignKey("budgets.id"), nullable=False, index=True)
    category_group_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    hidden: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    budget: Mapped["Budget"] = relationship(back_populates="categories")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
