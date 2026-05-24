"""Subscription Audit generator.

Clusters recurring same-payee + same-amount charges over a 90-day lookback.
A cluster qualifies as a subscription when it has at least three occurrences
and the intervals between them land within +/-20% of one canonical cadence
(weekly, monthly, quarterly, yearly).
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
from app.insights.schemas import Cadence, SubscriptionAuditData, TransactionRef
from app.snapshot.models import YnabSnapshot
from app.snapshot.queries import _internal_transfer_payee_ids, transactions_in_range

LOOKBACK_DAYS = 90
MIN_OCCURRENCES = 3
INTERVAL_TOLERANCE = 0.20  # +/-20%

# Canonical cadences and their (min, target, max) day ranges. Picked so the
# bands don't overlap and so realistic billing jitter (a charge that lands on
# a weekend gets posted 1-3 days later) stays inside the band.
_CADENCE_BANDS: tuple[tuple[Cadence, int, int, int], ...] = (
    ("weekly", 6, 7, 8),
    ("monthly", 28, 30, 32),
    ("quarterly", 85, 91, 95),
    ("yearly", 360, 365, 370),
)


def _classify_cadence(median_interval: float) -> Cadence | None:
    for name, lo, _target, hi in _CADENCE_BANDS:
        if lo <= median_interval <= hi:
            return name
    return None


def _intervals_consistent(intervals: list[int], median: float) -> bool:
    if median <= 0:
        return False
    threshold = median * INTERVAL_TOLERANCE
    return all(abs(i - median) <= max(threshold, 1.0) for i in intervals)


def _monthly_factor(cadence: Cadence) -> float:
    return {
        "weekly": 52 / 12,
        "monthly": 1.0,
        "quarterly": 1 / 3,
        "yearly": 1 / 12,
    }[cadence]


@dataclass
class _Cluster:
    payee_id: str
    payee_name: str
    amount_cents: int  # negative
    occurrences: list[TransactionRef]
    cadence: Cadence


@register_generator
class SubscriptionAuditGenerator(InsightGenerator):
    card_type: ClassVar[str] = "subscription_audit"
    cadence: ClassVar[str] = "weekly"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        start = today - timedelta(days=LOOKBACK_DAYS)
        rows = transactions_in_range(snapshot, start, today)
        payees_by_id = snapshot.payee_by_id()
        internal_transfers = _internal_transfer_payee_ids(snapshot)

        grouped: dict[tuple[str, int], list[TransactionRef]] = defaultdict(list)
        payee_names: dict[str, str] = {}
        for t in rows:
            if t.amount_cents >= 0:
                continue
            if t.payee_id is None:
                continue
            if t.payee_id in internal_transfers:
                continue
            payee = payees_by_id.get(t.payee_id)
            if payee is None:
                continue
            grouped[(t.payee_id, t.amount_cents)].append(
                TransactionRef(
                    id=t.id,
                    date=t.date,
                    amount_cents=t.amount_cents,
                    payee_name=payee.name,
                    memo=t.memo,
                )
            )
            payee_names[t.payee_id] = payee.name

        clusters: list[_Cluster] = []
        for (payee_id, amount_cents), occurrences in grouped.items():
            if len(occurrences) < MIN_OCCURRENCES:
                continue
            occurrences.sort(key=lambda o: o.date)
            intervals = [
                (occurrences[i].date - occurrences[i - 1].date).days
                for i in range(1, len(occurrences))
            ]
            if not intervals:
                continue
            median = statistics.median(intervals)
            cadence = _classify_cadence(median)
            if cadence is None:
                continue
            if not _intervals_consistent(intervals, median):
                continue
            clusters.append(
                _Cluster(
                    payee_id=payee_id,
                    payee_name=payee_names[payee_id],
                    amount_cents=amount_cents,
                    occurrences=occurrences,
                    cadence=cadence,
                )
            )

        outputs: list[GeneratedInsight] = []
        for cluster in clusters:
            outputs.append(await self._build_insight(cluster, anthropic_key))
        return outputs

    async def _build_insight(
        self, cluster: _Cluster, anthropic_key: SecretStr | None
    ) -> GeneratedInsight:
        absolute_cents = -cluster.amount_cents
        monthly_cost_cents = round(absolute_cents * _monthly_factor(cluster.cadence))
        annual_cost_cents = monthly_cost_cents * 12

        data = SubscriptionAuditData(
            payee_id=cluster.payee_id,
            payee_name=cluster.payee_name,
            cadence=cluster.cadence,
            amount_cents=absolute_cents,
            monthly_cost_cents=monthly_cost_cents,
            annual_cost_cents=annual_cost_cents,
            occurrences=cluster.occurrences,
            first_seen=cluster.occurrences[0].date,
            last_seen=cluster.occurrences[-1].date,
        )

        dollars = absolute_cents / 100
        monthly_dollars = monthly_cost_cents / 100
        fallback_title = f"${monthly_dollars:.2f}/mo to {cluster.payee_name}"
        fallback_summary = (
            f"Recurring {cluster.cadence} charge of ${dollars:.2f} to "
            f"{cluster.payee_name}. ${monthly_dollars:.2f}/month, "
            f"${annual_cost_cents / 100:,.2f}/year."
        )

        enhanced = await enhance_copy(
            anthropic_key=anthropic_key,
            fallback_title=fallback_title,
            fallback_summary=fallback_summary,
            card_type=self.card_type,
            payload=data.model_dump(mode="json"),
        )

        return GeneratedInsight(
            dedup_key=f"subscription:{cluster.payee_id}:{absolute_cents}:{cluster.cadence}",
            title=enhanced.title,
            summary=enhanced.summary,
            structured_data=data.model_dump(mode="json"),
            llm_enhanced=enhanced.used_llm,
        )
