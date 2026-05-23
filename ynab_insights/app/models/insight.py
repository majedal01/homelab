"""Persistence models for the Insights Feed.

`Insight` rows are produced by `InsightGenerator` implementations and rendered
as cards in the feed. `InsightRun` rows capture observability for every
generator execution (status, duration, error). Both are written out of band
of the API request path.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

if TYPE_CHECKING:
    from app.models.budget import Budget


class Insight(Base):
    __tablename__ = "insights"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    budget_id: Mapped[str] = mapped_column(ForeignKey("budgets.id"), nullable=False, index=True)
    card_type: Mapped[str] = mapped_column(String, nullable=False, index=True)
    dedup_key: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[str] = mapped_column(String, nullable=False)
    # JSON on SQLAlchemy maps to JSONB on Postgres and TEXT-with-JSON on SQLite.
    # Holds the discriminated payload typed by `app.schemas.insight`.
    structured_data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    refreshed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    llm_enhanced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    budget: Mapped["Budget"] = relationship()

    __table_args__ = (
        UniqueConstraint("budget_id", "dedup_key", name="uq_insights_budget_dedup"),
        Index(
            "ix_insights_feed",
            "budget_id",
            "dismissed_at",
            "refreshed_at",
        ),
    )


class InsightRun(Base):
    __tablename__ = "insight_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    card_type: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False, default="running")
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    insights_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    insights_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("ix_insight_runs_card_type_started", "card_type", "started_at"),
    )
