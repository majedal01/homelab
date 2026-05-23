"""Spending Anomaly generator.

For each category, compute weekly outflow over the trailing 13 weeks (current
week + 12 baseline weeks). Flag categories where the current week's spend
deviates from the baseline by both a `|z_score| >= 2.0` AND at least $25
in absolute terms (so a normally-zero category doesn't surface on a $5
single transaction).
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import AnomalyTopTransaction, SpendingAnomalyData
from app.models import Transaction
from app.services.queries import list_transactions

BASELINE_WEEKS = 12
MIN_ABSOLUTE_DEVIATION_CENTS = 2500  # $25
Z_SCORE_THRESHOLD = 2.0
TOP_TRANSACTIONS = 3


@dataclass
class _WeeklyAggregate:
    category_id: str
    category_name: str
    weekly_totals: list[int]  # oldest first; length == BASELINE_WEEKS + 1
    current_week_transactions: list[Transaction]


def _week_buckets(today: date) -> list[tuple[date, date]]:
    """Return (start, end) tuples for the trailing BASELINE_WEEKS + 1 weeks,
    oldest first. Each week is a 7-day window ending today (or 7 days prior)."""
    out: list[tuple[date, date]] = []
    # Most recent week is the 7 days up to and including today.
    for i in range(BASELINE_WEEKS, -1, -1):
        end = today - timedelta(days=7 * i)
        start = end - timedelta(days=6)
        out.append((start, end))
    return out


@register_generator
class SpendingAnomalyGenerator(InsightGenerator):
    card_type: ClassVar[str] = "spending_anomaly"
    cadence: ClassVar[str] = "weekly"

    async def run(
        self,
        session: AsyncSession,
        settings: Settings,
        budget_id: str,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        buckets = _week_buckets(today)
        lookback_start = buckets[0][0]
        txns = await list_transactions(
            session,
            budget_id=budget_id,
            date_from=lookback_start,
            date_to=today,
            limit=500,
        )

        # Index transactions by category, bucketed into the 13 weeks.
        per_category_weeks: dict[str, list[int]] = defaultdict(lambda: [0] * (BASELINE_WEEKS + 1))
        per_category_current: dict[str, list[Transaction]] = defaultdict(list)
        category_names: dict[str, str] = {}

        for t in txns:
            if t.amount_cents >= 0:
                continue
            if t.category_id is None or t.category is None:
                continue
            if t.payee is not None and t.payee.transfer_account_id is not None:
                continue
            # Find bucket index (last matching bucket wins; current week is last).
            idx: int | None = None
            for i, (start, end) in enumerate(buckets):
                if start <= t.date <= end:
                    idx = i
            if idx is None:
                continue
            per_category_weeks[t.category_id][idx] += -t.amount_cents
            category_names[t.category_id] = t.category.name
            if idx == BASELINE_WEEKS:
                per_category_current[t.category_id].append(t)

        outputs: list[GeneratedInsight] = []
        current_start, current_end = buckets[-1]

        for category_id, totals in per_category_weeks.items():
            baseline = totals[:BASELINE_WEEKS]
            current = totals[BASELINE_WEEKS]
            if current == 0:
                continue  # nothing happened this week; nothing to flag
            if not baseline or all(v == 0 for v in baseline):
                continue  # no signal to compare against
            mean = statistics.fmean(baseline)
            stdev = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
            if stdev == 0:
                continue
            z = (current - mean) / stdev
            absolute_dev = abs(current - mean)
            if abs(z) < Z_SCORE_THRESHOLD:
                continue
            if absolute_dev < MIN_ABSOLUTE_DEVIATION_CENTS:
                continue

            current_txns = sorted(
                per_category_current[category_id],
                key=lambda t: t.amount_cents,
            )[:TOP_TRANSACTIONS]
            top_refs = [
                AnomalyTopTransaction(
                    id=t.id,
                    date=t.date,
                    amount_cents=t.amount_cents,
                    payee_name=t.payee.name if t.payee else None,
                )
                for t in current_txns
            ]
            deviation_ratio = (current - mean) / mean if mean > 0 else 0.0

            data = SpendingAnomalyData(
                category_id=category_id,
                category_name=category_names[category_id],
                week_start=current_start,
                week_end=current_end,
                current_week_spend_cents=current,
                baseline_mean_cents=int(round(mean)),
                baseline_stdev_cents=int(round(stdev)),
                z_score=round(z, 2),
                deviation_ratio=round(deviation_ratio, 2),
                top_transactions=top_refs,
            )

            current_dollars = current / 100
            mean_dollars = mean / 100
            direction = "above" if z > 0 else "below"
            pct = abs(deviation_ratio) * 100
            fallback_title = f"{category_names[category_id]} spending is {direction} usual"
            fallback_summary = (
                f"You spent ${current_dollars:.0f} on "
                f"{category_names[category_id]} this week, "
                f"{pct:.0f}% {direction} your 12-week average of "
                f"${mean_dollars:.0f}."
            )

            enhanced = await enhance_copy(
                settings=settings,
                fallback_title=fallback_title,
                fallback_summary=fallback_summary,
                card_type=self.card_type,
                payload=data.model_dump(mode="json"),
            )

            week_label = current_start.isocalendar()
            outputs.append(
                GeneratedInsight(
                    dedup_key=(f"anomaly:{category_id}:{week_label.year}-W{week_label.week:02d}"),
                    title=enhanced.title,
                    summary=enhanced.summary,
                    structured_data=data.model_dump(mode="json"),
                    llm_enhanced=enhanced.used_llm,
                )
            )

        return outputs
