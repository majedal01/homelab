"""Spending Anomaly generator.

For each spending category, compute weekly outflow over the trailing 13
weeks (current week + 12 baseline weeks). Flag categories where the
current week's spend deviates from the baseline by |z_score| >= 2.0 AND
at least $25 in absolute terms.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import AnomalyTopTransaction, SpendingAnomalyData
from app.snapshot.models import Transaction, YnabSnapshot
from app.snapshot.queries import (
    _internal_transfer_payee_ids,
    _is_income_category,
    transactions_in_range,
)

BASELINE_WEEKS = 12
MIN_ABSOLUTE_DEVIATION_CENTS = 2500  # $25
Z_SCORE_THRESHOLD = 2.0
TOP_TRANSACTIONS = 3


@dataclass
class _Buckets:
    weekly_totals: list[int]
    current_week_txns: list[Transaction]


def _week_buckets(today: date) -> list[tuple[date, date]]:
    """Trailing BASELINE_WEEKS + 1 weeks, oldest first. Last entry is the current week."""
    out: list[tuple[date, date]] = []
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
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        buckets = _week_buckets(today)
        rows = transactions_in_range(snapshot, buckets[0][0], today)

        cat_by_id = snapshot.category_by_id()
        payees_by_id = snapshot.payee_by_id()
        on_budget = {a.id for a in snapshot.accounts if a.on_budget}
        internal_transfers = _internal_transfer_payee_ids(snapshot)

        per_cat: dict[str, _Buckets] = defaultdict(
            lambda: _Buckets(weekly_totals=[0] * (BASELINE_WEEKS + 1), current_week_txns=[])
        )
        cat_names: dict[str, str] = {}

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

            idx: int | None = None
            for i, (start, end) in enumerate(buckets):
                if start <= t.date <= end:
                    idx = i
            if idx is None:
                continue
            per_cat[t.category_id].weekly_totals[idx] += -t.amount_cents
            cat_names[t.category_id] = cat.name
            if idx == BASELINE_WEEKS:
                per_cat[t.category_id].current_week_txns.append(t)

        outputs: list[GeneratedInsight] = []
        current_start, current_end = buckets[-1]

        for category_id, b in per_cat.items():
            baseline = b.weekly_totals[:BASELINE_WEEKS]
            current = b.weekly_totals[BASELINE_WEEKS]
            if current == 0 or all(v == 0 for v in baseline):
                continue
            mean = statistics.fmean(baseline)
            stdev = statistics.pstdev(baseline) if len(baseline) > 1 else 0.0
            if stdev == 0:
                continue
            z = (current - mean) / stdev
            absolute_dev = abs(current - mean)
            if abs(z) < Z_SCORE_THRESHOLD or absolute_dev < MIN_ABSOLUTE_DEVIATION_CENTS:
                continue

            current_txns = sorted(
                b.current_week_txns,
                key=lambda t: t.amount_cents,
            )[:TOP_TRANSACTIONS]
            top_refs = [
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
            deviation_ratio = (current - mean) / mean if mean > 0 else 0.0

            data = SpendingAnomalyData(
                category_id=category_id,
                category_name=cat_names[category_id],
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
            fallback_title = f"{cat_names[category_id]} spending is {direction} usual"
            fallback_summary = (
                f"You spent ${current_dollars:.0f} on {cat_names[category_id]} "
                f"this week, {pct:.0f}% {direction} your 12-week average of "
                f"${mean_dollars:.0f}."
            )

            enhanced = await enhance_copy(
                anthropic_key=anthropic_key,
                fallback_title=fallback_title,
                fallback_summary=fallback_summary,
                card_type=self.card_type,
                payload=data.model_dump(mode="json"),
            )

            week_label = current_start.isocalendar()
            outputs.append(
                GeneratedInsight(
                    dedup_key=f"anomaly:{category_id}:{week_label.year}-W{week_label.week:02d}",
                    title=enhanced.title,
                    summary=enhanced.summary,
                    structured_data=data.model_dump(mode="json"),
                    llm_enhanced=enhanced.used_llm,
                )
            )

        return outputs
