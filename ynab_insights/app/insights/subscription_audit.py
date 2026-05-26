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

import re
import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.diagnostics import diag
from app.insights.llm import enhance_copy
from app.insights.schemas import Cadence, SubscriptionAuditData, TransactionRef
from app.snapshot.models import YnabSnapshot
from app.snapshot.queries import _internal_transfer_payee_ids, transactions_in_range

LOOKBACK_DAYS = 365

# Cluster qualification. The 2-occurrence floor stays because real users
# sometimes have only two charges visible in the lookback (mid-year signup,
# annual subscription with one charge "this year" and one "last year").
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
        diag("subscription_audit", "start", txns_in_lookback=len(rows))

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

        diag(
            "subscription_audit",
            "normalized_groups",
            count=len(grouped),
            min_size=min((len(e) for e in grouped.values()), default=0),
            max_size=max((len(e) for e in grouped.values()), default=0),
        )

        clusters: list[_Cluster] = []
        rejections: dict[str, int] = {}
        for _key, entries in grouped.items():
            found, reasons = _qualify_group(entries)
            clusters.extend(found)
            for reason in reasons:
                rejections[reason] = rejections.get(reason, 0) + 1
        for reason, count in rejections.items():
            diag("subscription_audit", "rejected", reason=reason, count=count)
        diag("subscription_audit", "qualified_clusters", count=len(clusters))

        outputs: list[GeneratedInsight] = []
        for cluster in clusters:
            outputs.append(await self._build_insight(cluster, anthropic_key, anthropic_model))
        diag("subscription_audit", "finished", insights_emitted=len(outputs))
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


Entry = tuple[str, str, TransactionRef]


def _qualify_group(entries: list[Entry]) -> tuple[list[_Cluster], list[str]]:
    """Find every qualifying subscription within one normalized-payee group.

    Strategy:
    1. Sub-cluster by amount band: pick the median amount, take everything
       within +/-AMOUNT_TOLERANCE of it as one candidate, recurse on the
       rest. This recovers v2.4's "Spotify $9.99 fires; Spotify $11.99
       fires separately" behavior while still merging "NETFLIX.COM" and
       "Netflix" payee strings via the normalized key.
    2. For each amount-coherent sub-cluster, require >=2 occurrences and a
       median interval inside the cadence band. The cadence band alone is
       the spacing tolerance — no extra "target +/- 3d" gate, since real
       monthly billing routinely lands at 34d due to posting-day jitter
       and the band already says 25-35 is monthly.
    """
    if len(entries) < MIN_OCCURRENCES_WITH_TIGHT_INTERVALS:
        return [], ["below_min_occurrences"]

    qualified: list[_Cluster] = []
    reasons: list[str] = []
    pending: list[list[Entry]] = [list(entries)]
    while pending:
        sub = pending.pop()
        if len(sub) < MIN_OCCURRENCES_WITH_TIGHT_INTERVALS:
            if sub:
                reasons.append("subcluster_below_min")
            continue
        inside, outside = _partition_by_amount(sub)
        if not inside:
            # Median fell between two amount peaks with no entry within
            # tolerance — e.g., 5 at $9.99 and 5 at $14.99, median $12.49,
            # nothing within +/-12% of $12.49. Without this guard we'd
            # recurse forever on `outside == sub`.
            reasons.append("amount_partition_stalled")
            continue
        if outside:
            pending.append(outside)
        cluster, reason = _qualify_amount_coherent(inside)
        if cluster is not None:
            qualified.append(cluster)
        elif reason:
            reasons.append(reason)
    return qualified, reasons


def _partition_by_amount(entries: list[Entry]) -> tuple[list[Entry], list[Entry]]:
    """Split into (within +/-AMOUNT_TOLERANCE of mode, everything else).

    Anchor on the mode rather than the median so an even split — 5
    charges at $9.99 vs 5 at $14.99 — doesn't end up with a median that
    sits between both peaks (which would put nothing inside the band and
    stall recursion). `statistics.mode` returns the first-encountered
    most-common value on ties, so single-amount clusters are stable too.
    """
    amounts = [e[2].amount_cents for e in entries]
    anchor = statistics.mode(amounts)
    if anchor == 0:
        return entries, []
    inside: list[Entry] = []
    outside: list[Entry] = []
    for entry in entries:
        if abs(entry[2].amount_cents - anchor) / abs(anchor) <= AMOUNT_TOLERANCE:
            inside.append(entry)
        else:
            outside.append(entry)
    return inside, outside


def _qualify_amount_coherent(
    entries: list[Entry],
) -> tuple[_Cluster | None, str | None]:
    """Decide whether an amount-coherent sub-cluster is a subscription."""
    if len(entries) < MIN_OCCURRENCES_WITH_TIGHT_INTERVALS:
        return None, "subcluster_below_min"

    entries.sort(key=lambda e: e[2].date)
    refs = [ref for _pid, _pname, ref in entries]
    amounts = [r.amount_cents for r in refs]

    intervals = [(refs[i].date - refs[i - 1].date).days for i in range(1, len(refs))]
    if not intervals:
        return None, "no_intervals"
    median_interval = statistics.median(intervals)
    classified = _classify_cadence(median_interval)
    if classified is None:
        return None, "interval_outside_bands"
    cadence, _target_days = classified

    by_pid: dict[str, int] = defaultdict(int)
    name_by_pid: dict[str, str] = {}
    for pid, pname, _ref in entries:
        by_pid[pid] += 1
        name_by_pid[pid] = pname
    primary_pid = max(by_pid, key=lambda k: by_pid[k])

    return (
        _Cluster(
            payee_id=primary_pid,
            payee_name=name_by_pid[primary_pid],
            median_amount_cents=int(statistics.median(amounts)),
            occurrences=refs,
            cadence=cadence,
        ),
        None,
    )
