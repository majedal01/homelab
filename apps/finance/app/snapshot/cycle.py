"""Per-category cycle classification.

A category's "cycle" is how often it naturally fires. Spending Anomaly and
Category Drift both need this signal so they can pick a comparison window
that doesn't lie:
- Comparing a monthly car payment to a weekly average is noise, not signal.
- Comparing a Q1 tax-prep spike to Q4 of the previous year is noise, too.

Classification is deterministic. The classifier looks at transaction
intervals over the trailing 12 months and returns one of:

- "weekly"     — high cadence (groceries, gas, coffee)
- "monthly"    — once-per-month with tight intervals (rent, car, utilities)
- "quarterly"  — every ~90 days (insurance premiums, estimated taxes)
- "annual"     — every ~365 days (property tax, school fees) — only
                 classifiable when the snapshot spans >=18 months
- "irregular"  — anything else; downstream generators should treat as
                 "no comparison window we trust"

`irregular` is the fail-safe default. Spending Anomaly and Category Drift
both skip irregular categories rather than fire a low-confidence card.
That keeps the feed quieter on hard-to-classify data instead of guessing.

LLM-aided classification was considered and skipped for v2.6f: an extra
per-category LLM call multiplies cost across 6 generators, and the
"irregular" fallback already produces the right downstream behavior
(skip the card). If the deterministic classifier proves too conservative
on real budgets we can add a `_maybe_llm_classify` path here.
"""

from __future__ import annotations

import statistics
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

from app.snapshot.models import Category, Transaction, YnabSnapshot
from app.snapshot.queries import _internal_transfer_payee_ids, _is_income_category

Cycle = Literal["weekly", "monthly", "quarterly", "annual", "irregular"]

# Trailing windows in days. Weekly/monthly/quarterly are evaluated against
# the last 12 months. Annual needs ~24 months of data so two yearly
# occurrences can both land in the window (one annual charge near today
# and the prior year's same charge ~365 days back leaves the older one
# barely outside an 18-month window when today drifts a few months past
# the most recent occurrence).
_RECENT_WINDOW_DAYS = 365
_ANNUAL_WINDOW_DAYS = 730
_ANNUAL_MIN_OCCURRENCES = 2

# Frequency shortcut: a category with this many txns in 365d is weekly,
# regardless of interval shape. Groceries average ~3-7/wk = 150-350/year.
# v2.6h lowers the floor (was 40) so a frequent-but-lumpy category — ~2+
# charges a month with messy spacing (Amazon, coffee, rideshare) — lands
# in weekly instead of failing the interval-shape checks and dropping to
# irregular.
_WEEKLY_FREQUENCY_FLOOR = 26

# Coefficient of variation of intervals must stay below this for the
# category to count as "regularly recurring." A true subscription has CoV
# ~0.05; clean monthly rent ~0.05; messy monthly with weekend jitter and
# the odd skipped month runs higher. v2.6h raises the ceiling (was 0.4) so
# real recurring spend with one or two irregular gaps still classifies
# rather than falling to irregular.
_MAX_INTERVAL_COV = 0.75

# Interval bands in days. v2.6h makes them CONTIGUOUS (no dead zones): the
# old bands left 11-19d (biweekly / semi-monthly), 46-59d, and 131-279d
# unclassifiable, so those categories fell to irregular and Spending
# Anomaly never evaluated them. Biweekly now reads as monthly (2 charges a
# month -> a monthly total is meaningful); the wider quarterly/annual bands
# only affect Category Drift, which evaluates those cadences.
_BANDS: tuple[tuple[Cycle, int, int], ...] = (
    ("weekly", 1, 10),
    ("monthly", 11, 45),
    ("quarterly", 46, 150),
    ("annual", 151, 430),
)


@dataclass(frozen=True)
class CycleClassification:
    """Why a category was classified the way it was.

    Generators only need `cycle`; the extra fields are for debugging
    surprise classifications and for the DESIGN.md examples.
    """

    cycle: Cycle
    occurrences: int
    median_interval_days: float | None
    interval_cov: float | None


def classify_category_cycle(
    snapshot: YnabSnapshot,
    category_id: str,
    *,
    today: date | None = None,
) -> CycleClassification:
    """Classify one category's natural cadence.

    Operates on on-budget transactions only, excluding internal transfers
    and income categories (consistent with the rest of the snapshot
    queries module).
    """
    today = today or date.today()
    on_budget = {a.id for a in snapshot.accounts if a.on_budget}
    transfers = _internal_transfer_payee_ids(snapshot)
    cat_by_id = snapshot.category_by_id()

    recent = _filter(
        snapshot.transactions,
        category_id=category_id,
        start=today - timedelta(days=_RECENT_WINDOW_DAYS),
        end=today,
        on_budget=on_budget,
        transfers=transfers,
        cat_by_id=cat_by_id,
    )

    if len(recent) >= _WEEKLY_FREQUENCY_FLOOR:
        return CycleClassification(
            cycle="weekly",
            occurrences=len(recent),
            median_interval_days=None,
            interval_cov=None,
        )

    if len(recent) < 3:
        # Not enough recent data to classify. Try annual with the
        # extended window before giving up.
        annual = _try_annual(
            snapshot=snapshot,
            category_id=category_id,
            today=today,
            on_budget=on_budget,
            transfers=transfers,
            cat_by_id=cat_by_id,
        )
        if annual is not None:
            return annual
        return CycleClassification(
            cycle="irregular",
            occurrences=len(recent),
            median_interval_days=None,
            interval_cov=None,
        )

    recent.sort(key=lambda t: t.date)
    intervals = [(recent[i].date - recent[i - 1].date).days for i in range(1, len(recent))]
    median = statistics.median(intervals)
    cov = _coefficient_of_variation(intervals, median)

    band = _band_for(median)
    if band is None or (cov is not None and cov > _MAX_INTERVAL_COV):
        # The classifier saw enough data but the spacing was too noisy
        # or fell between bands. Try annual via the wider window before
        # falling through to irregular.
        annual = _try_annual(
            snapshot=snapshot,
            category_id=category_id,
            today=today,
            on_budget=on_budget,
            transfers=transfers,
            cat_by_id=cat_by_id,
        )
        if annual is not None:
            return annual
        return CycleClassification(
            cycle="irregular",
            occurrences=len(recent),
            median_interval_days=median,
            interval_cov=cov,
        )

    return CycleClassification(
        cycle=band,
        occurrences=len(recent),
        median_interval_days=median,
        interval_cov=cov,
    )


def _try_annual(
    *,
    snapshot: YnabSnapshot,
    category_id: str,
    today: date,
    on_budget: set[str],
    transfers: set[str],
    cat_by_id: Mapping[str, Category],
) -> CycleClassification | None:
    """Re-run against an 18-month window to catch annual cadences."""
    txns = _filter(
        snapshot.transactions,
        category_id=category_id,
        start=today - timedelta(days=_ANNUAL_WINDOW_DAYS),
        end=today,
        on_budget=on_budget,
        transfers=transfers,
        cat_by_id=cat_by_id,
    )
    if len(txns) < _ANNUAL_MIN_OCCURRENCES:
        return None
    txns.sort(key=lambda t: t.date)
    intervals = [(txns[i].date - txns[i - 1].date).days for i in range(1, len(txns))]
    if not intervals:
        return None
    median = statistics.median(intervals)
    if not (_BANDS[-1][1] <= median <= _BANDS[-1][2]):
        return None
    cov = _coefficient_of_variation(intervals, median)
    return CycleClassification(
        cycle="annual",
        occurrences=len(txns),
        median_interval_days=median,
        interval_cov=cov,
    )


def _filter(
    transactions: Iterable[Transaction],
    *,
    category_id: str,
    start: date,
    end: date,
    on_budget: set[str],
    transfers: set[str],
    cat_by_id: Mapping[str, Category],
) -> list[Transaction]:
    out: list[Transaction] = []
    for t in transactions:
        if t.category_id != category_id:
            continue
        if t.account_id not in on_budget:
            continue
        if not (start <= t.date <= end):
            continue
        if t.payee_id is not None and t.payee_id in transfers:
            continue
        cat = cat_by_id.get(category_id)
        if cat is not None and _is_income_category(cat.name):
            continue
        out.append(t)
    return out


def _band_for(median: float) -> Cycle | None:
    for name, lo, hi in _BANDS:
        if lo <= median <= hi:
            return name
    return None


def _coefficient_of_variation(intervals: list[int], median: float) -> float | None:
    if len(intervals) < 2 or median <= 0:
        return None
    stdev = statistics.pstdev(intervals)
    return stdev / median
