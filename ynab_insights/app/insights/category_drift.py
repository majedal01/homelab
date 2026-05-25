"""Category Drift generator (v2.6f).

Two comparison modes, picked from the category's cycle classification:

- quarter_over_quarter (monthly / quarterly cycle): trailing 3 months vs
  the 9 months before that. Captures normal "things are creeping up"
  drift in steady-cadence categories.

- year_over_year (annual cycle, >= 15 months of data): trailing 3 months
  vs the same 3 calendar months one year prior. Avoids the false-drift
  trap where seasonal expenses (tax prep, holiday spending, school
  supplies) get compared against an unrelated quarter.

Categories whose cycle is irregular, or that have < 12 months of data,
are skipped. Spending Anomaly handles the short-history case; the
"no comparison window we trust" rule keeps the feed quiet rather than
firing low-confidence cards.

Thresholds stay at 15% pct floor + $50/mo dollar floor, both directions.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date
from typing import ClassVar, Literal

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import CategoryDriftData
from app.snapshot.cycle import classify_category_cycle
from app.snapshot.models import YnabSnapshot
from app.snapshot.queries import category_monthly_history

logger = logging.getLogger(__name__)

# 24 months: enough for both the 12-month QoQ shape and the year-over-year
# window. Categories with shorter history get filtered downstream.
LOOKBACK_MONTHS = 24
MIN_HISTORY_MONTHS = 12
YOY_MIN_HISTORY_MONTHS = 15
DRIFT_PCT_THRESHOLD = 0.15
DRIFT_DOLLARS_THRESHOLD_CENTS = 5000  # $50/mo


@register_generator
class CategoryDriftGenerator(InsightGenerator):
    card_type: ClassVar[str] = "category_drift"
    cadence: ClassVar[str] = "monthly"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        history = category_monthly_history(snapshot, LOOKBACK_MONTHS)
        if not history:
            return []
        today = date.today()
        outputs: list[GeneratedInsight] = []

        for cat in history:
            # category_monthly_history's last entry is the in-progress current
            # month, which would skew "trailing 3 months" by absorbing a
            # partial-month bucket. Drop it before any drift math.
            spend = [-x for x in cat.monthly_nets_cents[:-1]]
            # Need at least two active months to compute any kind of drift.
            # Irregular-cycle categories are filtered separately by the
            # classifier check below.
            active_months = sum(1 for v in spend if v > 0)
            if active_months < 2:
                continue

            classification = classify_category_cycle(snapshot, cat.category_id, today=today)
            cycle = classification.cycle
            if cycle == "irregular":
                continue

            if cycle == "annual":
                drift = _year_over_year_drift(spend)
                comparison_kind: Literal["quarter_over_quarter", "year_over_year"] = (
                    "year_over_year"
                )
            elif active_months >= MIN_HISTORY_MONTHS:
                # weekly / monthly / quarterly with full 12 months of activity:
                # standard QoQ drift.
                drift = _quarter_over_quarter_drift(spend[-MIN_HISTORY_MONTHS:])
                comparison_kind = "quarter_over_quarter"
            else:
                # Not enough months of activity for QoQ. Spending Anomaly's
                # shorter windows handle the recent-spike case.
                continue

            if drift is None:
                continue
            trail_avg, prior_avg, drift_pct, drift_cents = drift
            if abs(drift_pct) < DRIFT_PCT_THRESHOLD:
                continue
            if abs(drift_cents) < DRIFT_DOLLARS_THRESHOLD_CENTS:
                continue

            direction: Literal["up", "down"] = "up" if drift_cents > 0 else "down"
            display_history = spend[-MIN_HISTORY_MONTHS:]
            if len(display_history) < MIN_HISTORY_MONTHS:
                # Pad with zeros at the start so the schema's "12 oldest-first"
                # invariant holds even on shorter histories.
                pad = [0] * (MIN_HISTORY_MONTHS - len(display_history))
                display_history = pad + display_history

            data = CategoryDriftData(
                category_id=cat.category_id,
                category_name=cat.category_name,
                comparison_kind=comparison_kind,
                trailing_quarter_avg_cents=round(trail_avg),
                prior_three_quarters_avg_cents=round(prior_avg),
                drift_pct=round(drift_pct, 3),
                drift_cents_per_month=drift_cents,
                direction=direction,
                monthly_nets_cents=display_history,
            )

            pct_display = f"{abs(drift_pct) * 100:.0f}%"
            dollars_display = f"${abs(drift_cents) / 100:,.0f}"
            comparison_phrase = (
                "vs the same period last year"
                if comparison_kind == "year_over_year"
                else "vs the prior 9 months"
            )
            if direction == "up":
                fallback_title = f"{cat.category_name} is up {pct_display} {comparison_phrase}"
                fallback_summary = (
                    f"{cat.category_name} averaged {dollars_display}/mo more "
                    f"in the trailing quarter {comparison_phrase}."
                )
            else:
                fallback_title = f"{cat.category_name} is down {pct_display} {comparison_phrase}"
                fallback_summary = (
                    f"{cat.category_name} averaged {dollars_display}/mo less "
                    f"in the trailing quarter {comparison_phrase}. Room to reallocate."
                )

            enhanced = await enhance_copy(
                anthropic_key=anthropic_key,
                model=anthropic_model,
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


def _quarter_over_quarter_drift(
    spend_12mo: list[int],
) -> tuple[float, float, float, int] | None:
    """Trailing 3 months vs prior 9 months.

    Returns (trail_avg, prior_avg, drift_pct, drift_cents).
    """
    if len(spend_12mo) != 12:
        return None
    trail = spend_12mo[-3:]
    prior = spend_12mo[:-3]
    trail_avg = sum(trail) / len(trail)
    prior_avg = sum(prior) / len(prior)
    if prior_avg <= 0:
        return None
    drift_cents = round(trail_avg - prior_avg)
    drift_pct = (trail_avg - prior_avg) / prior_avg
    return trail_avg, prior_avg, drift_pct, drift_cents


def _year_over_year_drift(spend: list[int]) -> tuple[float, float, float, int] | None:
    """Trailing 3 months vs the same 3 calendar months one year prior.

    Needs at least 15 months of data: months[-15:-12] is the prior-year
    window for comparison against months[-3:].
    """
    if len(spend) < YOY_MIN_HISTORY_MONTHS:
        return None
    trail = spend[-3:]
    prior = spend[-15:-12]
    trail_avg = sum(trail) / len(trail)
    prior_avg = sum(prior) / len(prior)
    if prior_avg <= 0:
        return None
    drift_cents = round(trail_avg - prior_avg)
    drift_pct = (trail_avg - prior_avg) / prior_avg
    return trail_avg, prior_avg, drift_pct, drift_cents
