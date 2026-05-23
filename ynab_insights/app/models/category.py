from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, String
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

    # YNAB goal fields. All nullable; populated by the sync when the user has
    # configured a goal on the category. Powers the Goal Trajectory generator.
    goal_type: Mapped[str | None] = mapped_column(String, nullable=True)
    goal_target_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    goal_target_month: Mapped[date | None] = mapped_column(Date, nullable=True)
    goal_percentage_complete: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goal_overall_left_cents: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    goal_months_to_budget: Mapped[int | None] = mapped_column(Integer, nullable=True)

    budget: Mapped["Budget"] = relationship(back_populates="categories")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="category")
