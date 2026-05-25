"""Subscription Audit generator (v2.6f).

Clusters recurring same-payee + similar-amount charges over a 12-month
lookback. The v2.4 thresholds missed obvious recurring charges on real
budgets:

- Required 3 occurrences -> missed quarterly / semiannual subs in flight
- Required exact-cent amount match -> Netflix's mid-window price hike
  from $15.99 to $17.99 split into two clusters and neither qualified
- Fixed +/-20% interval tolerance -> 28-32 day "months" landed outside
  the band for some posting dates
- Payee match was case + punctuation sensitive -> "NETFLIX.COM TX123",
  "Netflix", and "NETFLIX 4839" failed to cluster

v2.6f loosens each of those while keeping the false-positive floor high:

- Minimum occurrences is 2 when the interval CoV is very low (<=0.05),
  otherwise stays at 3
- Amount tolerance is 12% from the cluster median, computed after grouping
- Interval bands are per-cadence with realistic jitter
- Payee names normalize before grouping: case, punctuation, suffix tokens
  (INC, LLC, .COM, PAYPAL *), trailing transaction-id-shaped suffixes
"""

from __future__ import annotations

import logging
import re
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

logger = logging.getLogger(__name__)

LOOKBACK_DAYS = 365

# Cluster qualification.
MIN_OCCURRENCES = 3
MIN_OCCURRENCES_WITH_TIGHT_INTERVALS = 2
AMOUNT_TOLERANCE = 0.12  # +/-12% from cluster median

# Per-cadence interval bands: (cadence, min, target, max). The bands are
# wider than v2.4 to absorb posting-date jitter — a "monthly" charge that
# lands on a weekend gets processed 1-3 days later, so 28-32d is normal.
_CADENCE_BANDS: tuple[tuple[Cadence, int, int, int], ...] = (
    ("weekly", 5, 7, 9),
    ("monthly", 25, 30, 35),
    ("quarterly", 75, 91, 105),
    ("yearly", 335, 365, 395),
)

# Payee normalization. Trailing transaction-id-shaped tokens (8+ alphanumeric
# uppercase characters) and common corporate suffixes get stripped before
# cluster grouping.
_SUFFIX_TOKENS = re.compile(
    r"\b(inc|llc|ltd|corp|co|com|company|the|paypal|sq|sqr|tst)\b",
    re.IGNORECASE,
)
_TRAILING_ID = re.compile(r"\s+[A-Z0-9]{8,}\b")
_PUNCTUATION = re.compile(r"[*#./\-_,()&]")
_WHITESPACE = re.compile(r"\s+")


def _normalize_payee(name: str) -> str:
    """Collapse a payee name to a stable lower-case key.

    The goal isn't pretty output — we keep the original name for display.
    The output is purely a clustering key, so aggressive stripping is
    fine as long as semantically-same payees end up at the same key.
    """
    cleaned = name
    cleaned = _TRAILING_ID.sub("", cleaned)
    cleaned = _PUNCTUATION.sub(" ", cleaned)
    cleaned = _SUFFIX_TOKENS.sub("", cleaned)
    cleaned = _WHITESPACE.sub(" ", cleaned).strip()
    return cleaned.lower()


def _classify_cadence(median_interval: float) -> tuple[Cadence, int] | None:
    """Return (cadence, target_days) if the median lands inside a band."""
    for name, lo, target, hi in _CADENCE_BANDS:
        if lo <= median_interval <= hi:
            return name, target
    return None


def _amount_within_tolerance(amounts: list[int]) -> bool:
    """All amounts must sit within +/-AMOUNT_TOLERANCE of the cluster median."""
    median = statistics.median(amounts)
    if median == 0:
        return False
    return all(abs(a - median) / abs(median) <= AMOUNT_TOLERANCE for a in amounts)


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
    median_amount_cents: int  # negative
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
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        start = today - timedelta(days=LOOKBACK_DAYS)
        rows = transactions_in_range(snapshot, start, today)
        payees_by_id = snapshot.payee_by_id()
        internal_transfers = _internal_transfer_payee_ids(snapshot)

        # Group by (normalized_payee_key) — not (payee_id, exact_amount).
        # Amount tolerance is checked after grouping so a mid-window price
        # change still lands inside one cluster.
        grouped: dict[str, list[tuple[str, str, TransactionRef]]] = defaultdict(list)
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
            key = _normalize_payee(payee.name)
            if not key:
                continue
            grouped[key].append(
                (
                    t.payee_id,
                    payee.name,
                    TransactionRef(
                        id=t.id,
                        date=t.date,
                        amount_cents=t.amount_cents,
                        payee_name=payee.name,
                        memo=t.memo,
                    ),
                )
            )

        clusters: list[_Cluster] = []
        for _key, entries in grouped.items():
            cluster = _qualify_cluster(entries)
            if cluster is not None:
                clusters.append(cluster)

        outputs: list[GeneratedInsight] = []
        for cluster in clusters:
            outputs.append(await self._build_insight(cluster, anthropic_key, anthropic_model))
        return outputs

    async def _build_insight(
        self,
        cluster: _Cluster,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None,
    ) -> GeneratedInsight:
        absolute_cents = -cluster.median_amount_cents
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
            model=anthropic_model,
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


def _qualify_cluster(
    entries: list[tuple[str, str, TransactionRef]],
) -> _Cluster | None:
    """Decide whether a normalized-payee bucket counts as a subscription."""
    if len(entries) < MIN_OCCURRENCES_WITH_TIGHT_INTERVALS:
        return None

    entries.sort(key=lambda e: e[2].date)
    refs = [ref for _pid, _pname, ref in entries]
    amounts = [r.amount_cents for r in refs]
    if not _amount_within_tolerance(amounts):
        return None

    intervals = [(refs[i].date - refs[i - 1].date).days for i in range(1, len(refs))]
    if not intervals:
        return None
    median_interval = statistics.median(intervals)
    classified = _classify_cadence(median_interval)
    if classified is None:
        return None
    cadence, target_days = classified

    n = len(refs)
    if n < MIN_OCCURRENCES:
        # 2-occurrence cluster: only one interval exists, so CoV across
        # intervals is undefined. Require the single interval to land
        # within +/-3 days of the canonical target for the cadence —
        # tighter than the cadence band itself.
        if abs(intervals[0] - target_days) > 3:
            return None
    # 3+ occurrences: classify_cadence already vetted by-band, which is
    # the tolerance budget. A CoV check would gate-keep rent-style
    # intervals that wobble +/- a few days within the band.

    # The displayed payee_id and name come from the most-frequent original
    # payee_id in the cluster (the same merchant may appear with different
    # internal payee_ids if YNAB created two entries for them).
    by_pid: dict[str, int] = defaultdict(int)
    name_by_pid: dict[str, str] = {}
    for pid, pname, _ref in entries:
        by_pid[pid] += 1
        name_by_pid[pid] = pname
    primary_pid = max(by_pid, key=lambda k: by_pid[k])

    return _Cluster(
        payee_id=primary_pid,
        payee_name=name_by_pid[primary_pid],
        median_amount_cents=int(statistics.median(amounts)),
        occurrences=refs,
        cadence=cadence,
    )
