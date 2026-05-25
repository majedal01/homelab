"""Spending Anomaly generator (v2.6f).

Cycle-aware comparison windows replace v2.4's "always trailing week vs
12-week average":

- Weekly-cycle categories (groceries, dining, gas): current week vs
  trailing 12 weeks (unchanged from v2.4)
- Monthly-cycle categories (rent, car payment, utilities): current
  month vs trailing 12 months
- Quarterly / annual / irregular: skipped — Category Drift owns the
  comparison logic for these (or the data is too noisy to detect)

Detection is more permissive (z=1.5, was 2.0) but the dollar floor is
higher ($50, was $25) so single-transaction noise stays quiet.
"""

from __future__ import annotations

import statistics
from calendar import monthrange
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import AnomalyTopTransaction, SpendingAnomalyData
from app.snapshot.cycle import Cycle, classify_category_cycle
from app.snapshot.models import Transaction, YnabSnapshot
from app.snapshot.queries import (
    _internal_transfer_payee_ids,
    _is_income_category,
    transactions_in_range,
)

BASELINE_WEEKS = 12
BASELINE_MONTHS = 12
MIN_ABSOLUTE_DEVIATION_CENTS = 5000  # $50
Z_SCORE_THRESHOLD = 1.5
TOP_TRANSACTIONS = 3


@dataclass
class _PeriodBuckets:
    """Per-category aggregation, generic across week and month modes."""

    period_totals: list[int]
    current_period_txns: list[Transaction]


def _week_buckets(today: date) -> list[tuple[date, date]]:
    """Trailing 13 weeks ending today. Last entry is the current week."""
    out: list[tuple[date, date]] = []
    for i in range(BASELINE_WEEKS, -1, -1):
        end = today - timedelta(days=7 * i)
        start = end - timedelta(days=6)
        out.append((start, end))
    return out


def _month_buckets(today: date) -> list[tuple[date, date]]:
    """Trailing 13 calendar months ending in today's month. Last entry is
    the current month-to-date."""
    out: list[tuple[date, date]] = []
    year, month = today.year, today.month
    months_back = BASELINE_MONTHS
    starts: list[tuple[int, int]] = []
    for _ in range(months_back + 1):
        starts.append((year, month))
        if month == 1:
            year, month = year - 1, 12
        else:
            month -= 1
    starts.reverse()
    for y, m in starts:
        start = date(y, m, 1)
        end = date(y, m, monthrange(y, m)[1])
        out.append((start, end))
    return out


@register_generator
class SpendingAnomalyGenerator(InsightGenerator):
    card_type: ClassVar[str] = "spending_anomaly"
    cadence: ClassVar[str] = "weekly"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        cat_by_id = snapshot.category_by_id()
        payees_by_id = snapshot.payee_by_id()
        on_budget = {a.id for a in snapshot.accounts if a.on_budget}
        internal_transfers = _internal_transfer_payee_ids(snapshot)

        # Group transactions per cycle to avoid recomputing on every
        # category. We classify each category's cycle once.
        weekly_buckets = _week_buckets(today)
        monthly_buckets = _month_buckets(today)
        window_start = min(weekly_buckets[0][0], monthly_buckets[0][0])
        rows = transactions_in_range(snapshot, window_start, today)

        # Pre-filter rows once.
        usable_rows: list[Transaction] = []
        for t in rows:
            if t.amount_cents >= 0:
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
            usable_rows.append(t)

        # Index usable rows by category for cycle classification + bucket fill.
        by_category: dict[str, list[Transaction]] = defaultdict(list)
        for t in usable_rows:
            assert t.category_id is not None  # checked above
            by_category[t.category_id].append(t)

        outputs: list[GeneratedInsight] = []
        for category_id, txns in by_category.items():
            classification = classify_category_cycle(snapshot, category_id, today=today)
            anomaly = _build_anomaly(
                txns,
                cycle=classification.cycle,
                today=today,
                weekly_buckets=weekly_buckets,
                monthly_buckets=monthly_buckets,
            )
            if anomaly is None:
                continue
            cat = cat_by_id[category_id]
            data = anomaly
            current_txns = sorted(
                [t for t in txns if data.period_start <= t.date <= data.period_end],
                key=lambda t: t.amount_cents,
            )[:TOP_TRANSACTIONS]
            data.category_id = category_id
            data.category_name = cat.name
            data.top_transactions = [
                AnomalyTopTransaction(
                    id=t.id,
                    date=t.date,
                    amount_cents=t.amount_cents,
                    payee_name=(
                        payees_by_id[t.payee_id].name
                        if t.payee_id and t.payee_id in payees_by_id
                        else None
                    ),
                )
                for t in current_txns
            ]

            mean_dollars = data.baseline_mean_cents / 100
            current_dollars = data.current_period_spend_cents / 100
            direction = "above" if data.z_score > 0 else "below"
            pct = abs(data.deviation_ratio) * 100
            cycle_word = "month" if data.cycle == "monthly" else "week"
            fallback_title = f"{cat.name} spending is {direction} usual"
            fallback_summary = (
                f"You spent ${current_dollars:.0f} on {cat.name} "
                f"this {cycle_word}, {pct:.0f}% {direction} your 12-"
                f"{cycle_word} average of ${mean_dollars:.0f}."
            )

            enhanced = await enhance_copy(
                anthropic_key=anthropic_key,
                model=anthropic_model,
                fallback_title=fallback_title,
                fallback_summary=fallback_summary,
                card_type=self.card_type,
                payload=data.model_dump(mode="json"),
            )

            dedup_key = _dedup_key(category_id, data.period_start, data.cycle)
            outputs.append(
                GeneratedInsight(
                    dedup_key=dedup_key,
                    title=enhanced.title,
                    summary=enhanced.summary,
                    structured_data=data.model_dump(mode="json"),
                    llm_enhanced=enhanced.used_llm,
                )
            )
        return outputs


def _build_anomaly(
    txns: list[Transaction],
    *,
    cycle: Cycle,
    today: date,
    weekly_buckets: list[tuple[date, date]],
    monthly_buckets: list[tuple[date, date]],
) -> SpendingAnomalyData | None:
    """Bucket spend per period and return the anomaly payload, if any.

    `data.category_id/name/top_transactions` are stubbed and overwritten
    by the caller — keeps this function pure on the spending math.
    """
    if cycle == "monthly":
        buckets = monthly_buckets
        baseline_n = BASELINE_MONTHS
    elif cycle == "weekly":
        buckets = weekly_buckets
        baseline_n = BASELINE_WEEKS
    else:
        # quarterly / annual / irregular: not this generator's job
        return None

    period_totals = [0] * (baseline_n + 1)
    for t in txns:
        for i, (start, end) in enumerate(buckets):
            if start <= t.date <= end:
                period_totals[i] += -t.amount_cents
                break

    baseline = period_totals[:baseline_n]
    current = period_totals[baseline_n]
    if current == 0 or all(v == 0 for v in baseline):
        return None

    mean = statistics.fmean(baseline)
    stdev = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
    if stdev == 0:
        return None

    z = (current - mean) / stdev
    absolute_dev = abs(current - mean)
    if abs(z) < Z_SCORE_THRESHOLD or absolute_dev < MIN_ABSOLUTE_DEVIATION_CENTS:
        return None

    deviation_ratio = (current - mean) / mean if mean > 0 else 0.0
    current_start, current_end = buckets[-1]
    # Clamp period_end to today on the month-to-date case so the label
    # doesn't claim spending into the future.
    period_end = min(current_end, today)
    return SpendingAnomalyData(
        category_id="",  # filled by caller
        category_name="",
        cycle=cycle,
        period_start=current_start,
        period_end=period_end,
        current_period_spend_cents=current,
        baseline_mean_cents=int(round(mean)),
        baseline_stdev_cents=int(round(stdev)),
        z_score=round(z, 2),
        deviation_ratio=round(deviation_ratio, 2),
        top_transactions=[],
    )


def _dedup_key(category_id: str, current_start: date, cycle: Cycle) -> str:
    if cycle == "monthly":
        return f"anomaly:{category_id}:{current_start.strftime('%Y-%m')}"
    iso = current_start.isocalendar()
    return f"anomaly:{category_id}:{iso.year}-W{iso.week:02d}"
