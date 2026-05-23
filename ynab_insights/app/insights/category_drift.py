"""Category Drift generator.

For each on-budget expense category, compares the trailing quarter's
monthly average to the average of the three prior quarters. Flags
categories where the drift exceeds both a percentage threshold (default
15%) and a dollar threshold ($50/mo). Both upward (overspending) and
downward (freed-up) drift surface.

Heuristic rationale lives in `docs/ynab-insights.md` under "Card type:
Category Drift".
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date
from typing import ClassVar, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import CategoryDriftData
from app.services.queries import category_monthly_history

logger = logging.getLogger(__name__)

LOOKBACK_MONTHS = 12
DRIFT_PCT_THRESHOLD = 0.15
DRIFT_DOLLARS_THRESHOLD_CENTS = 5000  # $50/mo


def _month_window() -> tuple[int, int]:
    """Returns (start_inclusive, end_inclusive) indexes into the 12-month
    array for the trailing quarter (months `[-3, -1]`, skipping the
    current incomplete month at index 11)."""
    return 8, 10


def _prior_window() -> tuple[int, int]:
    """Indexes for the three prior quarters: months `[-12, -4]`."""
    return 0, 7


@register_generator
class CategoryDriftGenerator(InsightGenerator):
    card_type: ClassVar[str] = "category_drift"
    cadence: ClassVar[str] = "monthly"

    async def run(
        self,
        session: AsyncSession,
        settings: Settings,
        budget_id: str,
    ) -> Sequence[GeneratedInsight]:
        history = await category_monthly_history(session, budget_id, LOOKBACK_MONTHS)
        if not history:
            return []

        today = date.today()
        outputs: list[GeneratedInsight] = []
        trail_lo, trail_hi = _month_window()
        prior_lo, prior_hi = _prior_window()

        for cat in history:
            if len(cat.monthly_nets_cents) != LOOKBACK_MONTHS:
                continue
            # Net is negative for outflow. Flip sign so we reason in
            # positive "spend per month" cents throughout.
            spend = [-x for x in cat.monthly_nets_cents]
            trail = spend[trail_lo : trail_hi + 1]
            prior = spend[prior_lo : prior_hi + 1]
            trail_avg = sum(trail) / len(trail)
            prior_avg = sum(prior) / len(prior)
            if prior_avg <= 0:
                # No baseline to compare against — skip to avoid divide-by-
                # zero noise (new category or one with only refund history).
                continue

            drift_cents = round(trail_avg - prior_avg)
            drift_pct = (trail_avg - prior_avg) / prior_avg

            if abs(drift_pct) < DRIFT_PCT_THRESHOLD:
                continue
            if abs(drift_cents) < DRIFT_DOLLARS_THRESHOLD_CENTS:
                continue

            direction: Literal["up", "down"] = "up" if drift_cents > 0 else "down"
            data = CategoryDriftData(
                category_id=cat.category_id,
                category_name=cat.category_name,
                trailing_quarter_avg_cents=round(trail_avg),
                prior_three_quarters_avg_cents=round(prior_avg),
                drift_pct=round(drift_pct, 3),
                drift_cents_per_month=drift_cents,
                direction=direction,
                monthly_nets_cents=spend,
            )

            pct_display = f"{abs(drift_pct) * 100:.0f}%"
            dollars_display = f"${abs(drift_cents) / 100:,.0f}"
            if direction == "up":
                fallback_title = f"{cat.category_name} is up {pct_display} vs the prior year"
                fallback_summary = (
                    f"{cat.category_name} averaged {dollars_display}/mo more "
                    f"in the last quarter than the three quarters before it."
                )
            else:
                fallback_title = f"{cat.category_name} is down {pct_display} vs the prior year"
                fallback_summary = (
                    f"{cat.category_name} averaged {dollars_display}/mo less "
                    f"in the last quarter — room to reallocate."
                )

            enhanced = await enhance_copy(
                settings=settings,
                fallback_title=fallback_title,
                fallback_summary=fallback_summary,
                card_type=self.card_type,
                payload=data.model_dump(mode="json"),
            )

            outputs.append(
                GeneratedInsight(
                    dedup_key=f"drift:{cat.category_id}:{today.strftime('%Y-%m')}",
                    title=enhanced.title,
                    summary=enhanced.summary,
                    structured_data=data.model_dump(mode="json"),
                    llm_enhanced=enhanced.used_llm,
                )
            )

        return outputs
