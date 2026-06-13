"""Goals generator (v2.6h): inferred progress.

Most users barely configure native YNAB goal targets, so the old
"X% toward your $Y goal" trajectory cards had little to work with and read
as noise. v2.6h replaces them with progress the app can INFER from data
that's always present in the snapshot:

- emergency_fund_coverage: liquid cash divided by average monthly spend,
  expressed as months of expenses. The primary card.
- savings_rate_trend: monthly savings rate over the trailing year. Secondary.

When neither can be computed (no cash/spend history, no income), the
generator falls back to the goal_setup_prompt empty-state card so the Goals
surface is never silently empty.

The generator keeps registering under card_type "goal_trajectory" (its slug
in the registry and the /generate route), but emits cards whose own
card_type is set explicitly via GeneratedInsight.card_type. Native
per-category trajectory cards are no longer emitted; the goal_trajectory
card type and its renderer remain for backward compatibility.
"""

from __future__ import annotations

import statistics
from collections.abc import Sequence
from datetime import date, timedelta
from typing import ClassVar, Literal

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.diagnostics import diag
from app.insights.llm import enhance_copy
from app.insights.schemas import (
    EmergencyFundCoverageData,
    GoalSetupPromptCategory,
    GoalSetupPromptData,
    SavingsRatePoint,
    SavingsRateTrendData,
)
from app.snapshot.models import YnabSnapshot
from app.snapshot.queries import cash_balance_cents, monthly_trend, spending_by_category

# Trailing complete months averaged for the emergency-fund denominator.
EMERGENCY_FUND_MONTHS = 6
MIN_MONTHS_FOR_EMERGENCY_FUND = 2
# Trailing months charted for the savings-rate trend.
SAVINGS_TREND_MONTHS = 12
MIN_MONTHS_WITH_INCOME = 3
# Half-over-half change above this (in rate points) reads as a real move.
SAVINGS_DIRECTION_EPSILON = 0.02


@register_generator
class GoalTrajectoryGenerator(InsightGenerator):
    card_type: ClassVar[str] = "goal_trajectory"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        diag("goal_trajectory", "start", accounts=len(snapshot.accounts))

        outputs: list[GeneratedInsight] = []
        emergency = await self._build_emergency_fund(
            snapshot, today, anthropic_key, anthropic_model
        )
        if emergency is not None:
            outputs.append(emergency)
        savings = await self._build_savings_rate(snapshot, today, anthropic_key, anthropic_model)
        if savings is not None:
            outputs.append(savings)

        if not outputs:
            prompt = _build_empty_state_prompt(snapshot, today)
            diag("goal_trajectory", "empty_state", reason="no_inferred_progress")
            return [prompt] if prompt is not None else []

        diag("goal_trajectory", "finished", insights_emitted=len(outputs))
        return outputs

    async def _build_emergency_fund(
        self,
        snapshot: YnabSnapshot,
        today: date,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None,
    ) -> GeneratedInsight | None:
        cash = cash_balance_cents(snapshot)
        # Trailing complete months (drop the current partial month).
        trend = monthly_trend(snapshot, EMERGENCY_FUND_MONTHS + 1)[:-1]
        spends = [m.spending_cents for m in trend if m.spending_cents > 0]
        if cash < 0 or len(spends) < MIN_MONTHS_FOR_EMERGENCY_FUND:
            diag("goal_trajectory", "skip_emergency_fund", months=len(spends), cash_neg=cash < 0)
            return None
        avg_spend = round(statistics.fmean(spends))
        if avg_spend <= 0:
            return None
        coverage = round(cash / avg_spend, 1)

        data = EmergencyFundCoverageData(
            cash_balance_cents=cash,
            avg_monthly_spending_cents=avg_spend,
            coverage_months=coverage,
            months_of_history=len(spends),
        )
        cash_d = cash / 100
        avg_d = avg_spend / 100
        fallback_title = f"Emergency fund: {coverage:.1f} months of expenses"
        fallback_summary = (
            f"Your ${cash_d:,.0f} in cash covers about {coverage:.1f} months at your "
            f"recent ${avg_d:,.0f}/mo spending. A common target is "
            f"{data.target_months} months."
        )
        enhanced = await enhance_copy(
            anthropic_key=anthropic_key,
            model=anthropic_model,
            fallback_title=fallback_title,
            fallback_summary=fallback_summary,
            card_type="emergency_fund_coverage",
            payload=data.model_dump(mode="json"),
        )
        return GeneratedInsight(
            dedup_key=f"emergency_fund:{snapshot.budget_id}:{today.strftime('%Y-%m')}",
            title=enhanced.title,
            summary=enhanced.summary,
            structured_data=data.model_dump(mode="json"),
            llm_enhanced=enhanced.used_llm,
            card_type="emergency_fund_coverage",
        )

    async def _build_savings_rate(
        self,
        snapshot: YnabSnapshot,
        today: date,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None,
    ) -> GeneratedInsight | None:
        # Trailing complete months (drop the current partial month).
        trend = monthly_trend(snapshot, SAVINGS_TREND_MONTHS + 1)[:-1]
        points: list[SavingsRatePoint] = []
        rates: list[float] = []
        for m in trend:
            if m.income_cents > 0:
                rate = round((m.income_cents - m.spending_cents) / m.income_cents, 3)
                points.append(SavingsRatePoint(year=m.year, month=m.month, savings_rate=rate))
                rates.append(rate)
            else:
                points.append(SavingsRatePoint(year=m.year, month=m.month, savings_rate=None))
        if len(rates) < MIN_MONTHS_WITH_INCOME:
            diag("goal_trajectory", "skip_savings_rate", months_with_income=len(rates))
            return None

        average = round(statistics.fmean(rates), 3)
        latest = rates[-1]
        direction = _savings_direction(rates)
        data = SavingsRateTrendData(
            points=points,
            average_savings_rate=average,
            latest_savings_rate=latest,
            direction=direction,
            months_of_history=len(rates),
        )
        avg_pct = average * 100
        latest_pct = latest * 100
        move = {"up": "trending up", "down": "trending down", "flat": "holding steady"}[direction]
        fallback_title = f"Savings rate: {latest_pct:.0f}% last month, {move}"
        fallback_summary = (
            f"Over the past {len(rates)} months with income you saved "
            f"{avg_pct:.0f}% on average; the most recent month was {latest_pct:.0f}%."
        )
        enhanced = await enhance_copy(
            anthropic_key=anthropic_key,
            model=anthropic_model,
            fallback_title=fallback_title,
            fallback_summary=fallback_summary,
            card_type="savings_rate_trend",
            payload=data.model_dump(mode="json"),
        )
        return GeneratedInsight(
            dedup_key=f"savings_rate:{snapshot.budget_id}:{today.strftime('%Y-%m')}",
            title=enhanced.title,
            summary=enhanced.summary,
            structured_data=data.model_dump(mode="json"),
            llm_enhanced=enhanced.used_llm,
            card_type="savings_rate_trend",
        )


def _savings_direction(rates: list[float]) -> Literal["up", "down", "flat"]:
    """Compare the back half of the series to the front half."""
    if len(rates) < 4:
        return "flat"
    mid = len(rates) // 2
    older = statistics.fmean(rates[:mid])
    newer = statistics.fmean(rates[mid:])
    delta = newer - older
    if delta > SAVINGS_DIRECTION_EPSILON:
        return "up"
    if delta < -SAVINGS_DIRECTION_EPSILON:
        return "down"
    return "flat"


def _build_empty_state_prompt(snapshot: YnabSnapshot, today: date) -> GeneratedInsight | None:
    """Build the goal_setup_prompt card listing top spending categories.

    Ranks by trailing 90d spend so the categories feel current. Returns
    None on a snapshot with literally no expense activity (the empty
    prompt would be a useless card with no candidates to suggest)."""
    ninety_days_ago = today - timedelta(days=90)
    top = spending_by_category(snapshot, ninety_days_ago, today)
    # Only include real categories; the "Uncategorized" pseudo-id with
    # category_id=None wouldn't be settable as a YNAB goal.
    candidates = [row for row in top if row.category_id is not None][:5]
    if not candidates:
        return None

    payload = GoalSetupPromptData(
        top_categories=[
            GoalSetupPromptCategory(
                category_id=row.category_id,  # type: ignore[arg-type]
                category_name=row.category_name or "Uncategorized",
                # spent_cents is negative net spend; flip to positive.
                monthly_avg_spend_cents=round(-row.spent_cents / 3),
            )
            for row in candidates
        ]
    )

    return GeneratedInsight(
        dedup_key=f"goal_setup_prompt:{snapshot.budget_id}:{today.strftime('%Y-%m')}",
        title="Set a goal to start tracking",
        summary=(
            "No goals are set in YNAB yet. Pick one of your top spending "
            "categories and set a target to see projected trajectories here."
        ),
        structured_data=payload.model_dump(mode="json"),
        llm_enhanced=False,
        card_type="goal_setup_prompt",
    )
