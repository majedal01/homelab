"""Category Projection generator (v2.6g).

For each of the top spending categories, projects this month's end-of-month
spend from month-to-date pace, then compares against the trailing 12-month
monthly average. Fires when the projection diverges materially.

Different from Spending Anomaly (which compares completed periods) and
Category Drift (which compares trailing 3 months to prior 9 months):
this one looks AHEAD — "based on what you've spent through day N of
this month, you're on track for $X by month-end vs your usual $Y."

The forecasting math is intentionally simple linear extrapolation:
`projected = (mtd_spend / days_into_month) * days_in_month`. Anything
fancier (seasonality, day-of-week weighting) introduces failure modes
that are harder to explain in the UI. The card surfaces both numbers
so the user can sanity-check.
"""

from __future__ import annotations

from calendar import monthrange
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar, Literal

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.diagnostics import diag
from app.insights.llm import enhance_copy
from app.insights.schemas import (
    CategoryProjectionData,
    CategoryProjectionTopTransaction,
)
from app.snapshot.models import Transaction, YnabSnapshot
from app.snapshot.queries import (
    _internal_transfer_payee_ids,
    _is_income_category,
    spending_by_category,
)

TOP_CATEGORIES = 5
LOOKBACK_DAYS = 90  # for ranking top spenders
BASELINE_MONTHS = 12
MIN_DAYS_INTO_MONTH = 5
DELTA_PCT_THRESHOLD = 0.15
DELTA_DOLLARS_THRESHOLD_CENTS = 5000  # $50


@dataclass(frozen=True)
class _Projection:
    category_id: str
    category_name: str
    month_to_date_cents: int
    projected_month_end_cents: int
    baseline_monthly_avg_cents: int
    delta_cents: int
    delta_pct: float
    days_into_month: int
    days_in_month: int


@register_generator
class CategoryProjectionGenerator(InsightGenerator):
    card_type: ClassVar[str] = "category_projection"
    cadence: ClassVar[str] = "weekly"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        days_into_month = today.day
        diag(
            "category_projection",
            "start",
            day_of_month=days_into_month,
        )
        if days_into_month < MIN_DAYS_INTO_MONTH:
            # Pace is too noisy early in the month — one $500 purchase on
            # day 2 projects to $7500 month-end. Skip; the next regen will
            # catch up.
            diag(
                "category_projection",
                "skipped",
                reason="too_early_in_month",
                day_of_month=days_into_month,
            )
            return []

        month_start = date(today.year, today.month, 1)
        days_in_month = monthrange(today.year, today.month)[1]
        ninety_days_ago = today - timedelta(days=LOOKBACK_DAYS)

        # Rank top spenders by trailing 90d. spending_by_category already
        # excludes income + internal transfers.
        top = spending_by_category(snapshot, ninety_days_ago, today)[:TOP_CATEGORIES]
        diag("category_projection", "top_categories", count=len(top))

        # Build a category_id -> trailing 12mo baseline lookup once.
        twelve_months_ago = date(
            today.year if today.month > 12 else today.year - 1,
            (today.month - 12) % 12 + (1 if today.month <= 12 else 0),
            1,
        )
        # Simpler: subtract days; we just need ~12mo of spend totals.
        twelve_months_ago = today - timedelta(days=365)
        baselines = _per_category_monthly_baseline(snapshot, twelve_months_ago, month_start)

        # Build a category_id -> this-month transactions index.
        mtd_by_cat: dict[str, list[Transaction]] = {}
        on_budget = {a.id for a in snapshot.accounts if a.on_budget}
        internal_transfers = _internal_transfer_payee_ids(snapshot)
        cat_by_id = snapshot.category_by_id()
        payees_by_id = snapshot.payee_by_id()
        for t in snapshot.transactions:
            if not (month_start <= t.date <= today):
                continue
            if t.account_id not in on_budget:
                continue
            if t.payee_id is not None and t.payee_id in internal_transfers:
                continue
            if t.category_id is None:
                continue
            cat = cat_by_id.get(t.category_id)
            if cat is None or _is_income_category(cat.name):
                continue
            if t.amount_cents >= 0:
                continue
            mtd_by_cat.setdefault(t.category_id, []).append(t)

        projections: list[_Projection] = []
        rejections: dict[str, int] = {}
        for row in top:
            if row.category_id is None:
                continue
            cat_id = row.category_id
            mtd_txns = mtd_by_cat.get(cat_id, [])
            mtd_cents = sum(-t.amount_cents for t in mtd_txns)
            baseline = baselines.get(cat_id, 0)
            if baseline <= 0:
                rejections["no_baseline"] = rejections.get("no_baseline", 0) + 1
                continue
            projected = round(mtd_cents / days_into_month * days_in_month)
            delta_cents = projected - baseline
            delta_pct = delta_cents / baseline if baseline > 0 else 0.0
            if abs(delta_cents) < DELTA_DOLLARS_THRESHOLD_CENTS:
                rejections["below_dollar_threshold"] = (
                    rejections.get("below_dollar_threshold", 0) + 1
                )
                continue
            if abs(delta_pct) < DELTA_PCT_THRESHOLD:
                rejections["below_pct_threshold"] = rejections.get("below_pct_threshold", 0) + 1
                continue
            projections.append(
                _Projection(
                    category_id=cat_id,
                    category_name=row.category_name or "Uncategorized",
                    month_to_date_cents=mtd_cents,
                    projected_month_end_cents=projected,
                    baseline_monthly_avg_cents=baseline,
                    delta_cents=delta_cents,
                    delta_pct=delta_pct,
                    days_into_month=days_into_month,
                    days_in_month=days_in_month,
                )
            )

        for reason, count in rejections.items():
            diag("category_projection", "rejected", reason=reason, count=count)

        outputs: list[GeneratedInsight] = []
        for p in projections:
            top_txns = sorted(
                mtd_by_cat.get(p.category_id, []),
                key=lambda t: t.amount_cents,
            )[:5]
            top_refs = [
                CategoryProjectionTopTransaction(
                    id=t.id,
                    date=t.date,
                    amount_cents=t.amount_cents,
                    payee_name=(
                        payees_by_id[t.payee_id].name
                        if t.payee_id and t.payee_id in payees_by_id
                        else None
                    ),
                )
                for t in top_txns
            ]
            direction: Literal["over", "under"] = "over" if p.delta_cents > 0 else "under"
            data = CategoryProjectionData(
                category_id=p.category_id,
                category_name=p.category_name,
                month_start=month_start,
                days_into_month=p.days_into_month,
                days_in_month=p.days_in_month,
                month_to_date_cents=p.month_to_date_cents,
                projected_month_end_cents=p.projected_month_end_cents,
                baseline_monthly_avg_cents=p.baseline_monthly_avg_cents,
                delta_cents=p.delta_cents,
                delta_pct=round(p.delta_pct, 3),
                direction=direction,
                top_transactions=top_refs,
            )

            projected_dollars = p.projected_month_end_cents / 100
            baseline_dollars = p.baseline_monthly_avg_cents / 100
            delta_dollars = abs(p.delta_cents) / 100
            if direction == "over":
                fallback_title = (
                    f"{p.category_name}: on pace for ${projected_dollars:,.0f} this month"
                )
                fallback_summary = (
                    f"Trailing-12-month average for {p.category_name} is "
                    f"${baseline_dollars:,.0f}/mo. At today's pace you'd land "
                    f"${delta_dollars:,.0f} over."
                )
            else:
                fallback_title = f"{p.category_name}: pacing ${delta_dollars:,.0f} under usual"
                fallback_summary = (
                    f"At today's pace {p.category_name} would land at "
                    f"${projected_dollars:,.0f} this month vs your typical "
                    f"${baseline_dollars:,.0f}/mo."
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
                    dedup_key=(f"projection:{p.category_id}:{month_start.strftime('%Y-%m')}"),
                    title=enhanced.title,
                    summary=enhanced.summary,
                    structured_data=data.model_dump(mode="json"),
                    llm_enhanced=enhanced.used_llm,
                )
            )

        diag("category_projection", "finished", insights_emitted=len(outputs))
        return outputs


def _per_category_monthly_baseline(
    snapshot: YnabSnapshot,
    window_start: date,
    window_end: date,
) -> dict[str, int]:
    """Sum on-budget spend per category over [window_start, window_end] and
    divide by the number of calendar months in the window. Returns positive
    cents per month per category.

    Excludes the current month so the baseline reflects "what you usually
    spend" rather than this-month-to-date.
    """
    on_budget = {a.id for a in snapshot.accounts if a.on_budget}
    internal_transfers = _internal_transfer_payee_ids(snapshot)
    cat_by_id = snapshot.category_by_id()
    totals: dict[str, int] = {}
    for t in snapshot.transactions:
        if not (window_start <= t.date < window_end):
            continue
        if t.account_id not in on_budget:
            continue
        if t.payee_id is not None and t.payee_id in internal_transfers:
            continue
        if t.category_id is None:
            continue
        cat = cat_by_id.get(t.category_id)
        if cat is None or _is_income_category(cat.name):
            continue
        if t.amount_cents >= 0:
            continue
        totals[t.category_id] = totals.get(t.category_id, 0) + (-t.amount_cents)
    span_days = max((window_end - window_start).days, 1)
    months = max(span_days / 30.4, 1.0)
    return {cid: round(v / months) for cid, v in totals.items()}
