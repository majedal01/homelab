"""Typed payloads for `Insight.structured_data`.

Each card type has its own Pydantic model. The frontend reads
`structured_data.card_type` as the discriminator and switches on it to
pick the matching card component. We expose the union through the
`/api/insights` schemas so OpenAPI generation produces a clean `oneOf`
for `openapi-typescript` to turn into a TS discriminated union.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field

CardType = Literal[
    "subscription_audit",
    "spending_anomaly",
    "cashflow_forecast",
    "goal_trajectory",
]

Cadence = Literal["weekly", "monthly", "quarterly", "yearly"]


class TransactionRef(BaseModel):
    """Minimal pointer to a transaction so the detail view can re-resolve it."""

    id: str
    date: date
    amount_cents: int
    payee_name: str | None = None
    memo: str | None = None


class SubscriptionAuditData(BaseModel):
    card_type: Literal["subscription_audit"] = "subscription_audit"
    payee_id: str
    payee_name: str
    cadence: Cadence
    amount_cents: int
    monthly_cost_cents: int
    annual_cost_cents: int
    occurrences: list[TransactionRef]
    first_seen: date
    last_seen: date


class AnomalyTopTransaction(BaseModel):
    id: str
    date: date
    amount_cents: int
    payee_name: str | None = None


class SpendingAnomalyData(BaseModel):
    card_type: Literal["spending_anomaly"] = "spending_anomaly"
    category_id: str
    category_name: str
    week_start: date
    week_end: date
    current_week_spend_cents: int
    baseline_mean_cents: int
    baseline_stdev_cents: int
    z_score: float
    deviation_ratio: float
    top_transactions: list[AnomalyTopTransaction]


class CategoryRate(BaseModel):
    category_id: str | None
    category_name: str
    monthly_average_cents: int


class CashflowForecastData(BaseModel):
    card_type: Literal["cashflow_forecast"] = "cashflow_forecast"
    starting_balance_cents: int
    daily_net_cents: int
    projected_30d_cents: int
    projected_60d_cents: int
    projected_90d_cents: int
    lookback_days: int
    top_spending_categories: list[CategoryRate]


class GoalTrajectoryData(BaseModel):
    card_type: Literal["goal_trajectory"] = "goal_trajectory"
    category_id: str
    category_name: str
    goal_type: str
    target_cents: int
    progress_cents: int
    remaining_cents: int
    percent_complete: int
    current_monthly_contribution_cents: int
    target_date: date | None
    projected_completion_date: date | None
    months_to_target: int | None
    on_track: bool | None


InsightStructuredData = Annotated[
    SubscriptionAuditData
    | SpendingAnomalyData
    | CashflowForecastData
    | GoalTrajectoryData,
    Field(discriminator="card_type"),
]


class InsightResponse(BaseModel):
    id: int
    budget_id: str
    card_type: CardType
    dedup_key: str
    title: str
    summary: str
    structured_data: InsightStructuredData
    generated_at: datetime
    refreshed_at: datetime
    dismissed_at: datetime | None
    llm_enhanced: bool


class InsightRunResponse(BaseModel):
    id: int
    card_type: str
    started_at: datetime
    finished_at: datetime | None
    status: str
    duration_ms: int | None
    insights_created: int
    insights_updated: int
    error: str | None


class GenerateResponse(BaseModel):
    run_ids: list[int]
