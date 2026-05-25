"""Year in Money generator (v2.6f).

On-demand retrospective. Picks the widest window the snapshot supports:

- Snapshot spans >= 365 days -> annual variant ("Your last 12 months").
- Snapshot spans >= 90 days  -> quarterly variant ("Your last 90 days").
- Less than 90 days -> no card.

Calendar-anchored triggers (Jan 1 for annual, Apr/Jul/Oct 1 for quarterly)
were dropped in v2.6f. A stateless, on-demand app shouldn't gate the
biggest summary card on the user happening to log in on the first of a
quarter — most sessions never saw it.
"""

from __future__ import annotations

import logging
from calendar import monthrange
from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from typing import ClassVar, Literal

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import (
    YearInMoneyBiggestSingle,
    YearInMoneyData,
    YearInMoneyTopCategory,
    YearInMoneyTopPayee,
)
from app.snapshot.models import YnabSnapshot
from app.snapshot.queries import (
    _internal_transfer_payee_ids,
    _is_income_category,
    period_summary,
)

logger = logging.getLogger(__name__)

ANNUAL_DAYS = 365
QUARTERLY_DAYS = 90


def _period_bounds(
    snapshot: YnabSnapshot,
    today: date,
) -> tuple[Literal["annual", "quarterly"], date, date, str] | None:
    """Pick the widest retrospective window the snapshot can support.

    Returns (kind, start, end, label) or None if the snapshot doesn't
    have enough history. End is always `today` so the user sees their
    most recent activity rather than an arbitrary calendar boundary.
    """
    if not snapshot.transactions:
        return None
    oldest = min(t.date for t in snapshot.transactions)
    span_days = (today - oldest).days
    if span_days >= ANNUAL_DAYS:
        start = today - timedelta(days=ANNUAL_DAYS)
        return ("annual", start, today, "last 12 months")
    if span_days >= QUARTERLY_DAYS:
        start = today - timedelta(days=QUARTERLY_DAYS)
        return ("quarterly", start, today, "last 90 days")
    return None


def _months_in_window(start: date, end: date) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1
            y += 1
    return out


@register_generator
class YearInMoneyGenerator(InsightGenerator):
    card_type: ClassVar[str] = "year_in_money"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        bounds = _period_bounds(snapshot, today)
        if bounds is None:
            return []
        kind, start, end, label = bounds

        summary = period_summary(snapshot, start, end)
        if summary.transaction_count == 0:
            return []

        on_budget = {a.id for a in snapshot.accounts if a.on_budget}
        cat_by_id = snapshot.category_by_id()
        payees_by_id = snapshot.payee_by_id()
        internal_transfers = _internal_transfer_payee_ids(snapshot)

        # Top 3 categories by net spend.
        top_categories = [
            YearInMoneyTopCategory(
                category_id=row.category_id,
                category_name=row.category_name or "Uncategorized",
                net_spend_cents=-row.net_cents,
            )
            for row in summary.by_category
            if row.net_cents < 0
        ][:3]

        # Top 5 payees by total outflow (in-range, excluding income + transfers).
        payee_amounts: dict[str | None, int] = defaultdict(int)
        payee_counts: dict[str | None, int] = defaultdict(int)
        payee_names: dict[str | None, str] = {}
        biggest: YearInMoneyBiggestSingle | None = None
        biggest_amount = 0

        for t in snapshot.transactions:
            if t.account_id not in on_budget:
                continue
            if not (start <= t.date <= end):
                continue
            if t.payee_id is not None and t.payee_id in internal_transfers:
                continue
            cat = cat_by_id.get(t.category_id) if t.category_id else None
            cat_name = cat.name if cat else None
            if t.category_id is None or _is_income_category(cat_name):
                continue
            if t.amount_cents >= 0:
                continue
            outflow = -t.amount_cents  # positive
            payee_amounts[t.payee_id] += outflow
            payee_counts[t.payee_id] += 1
            if t.payee_id is not None:
                payee = payees_by_id.get(t.payee_id)
                payee_names[t.payee_id] = payee.name if payee else "Unknown"
            if t.amount_cents < biggest_amount:
                biggest_amount = t.amount_cents
                biggest = YearInMoneyBiggestSingle(
                    transaction_id=t.id,
                    date=t.date,
                    amount_cents=t.amount_cents,
                    payee_name=payee_names.get(t.payee_id),
                    category_name=cat_name,
                )

        top_payee_ids = sorted(payee_amounts, key=lambda p: payee_amounts[p], reverse=True)[:5]
        top_payees = [
            YearInMoneyTopPayee(
                payee_id=pid,
                payee_name=payee_names.get(pid, "Uncategorized payee"),
                transaction_count=payee_counts[pid],
                amount_cents=payee_amounts[pid],
            )
            for pid in top_payee_ids
        ]

        # Monthly savings-rate series.
        months = _months_in_window(start, end)
        savings_rate_trend: list[float | None] = []
        for y, m in months:
            month_start = date(y, m, 1)
            month_end = date(y, m, monthrange(y, m)[1])
            month_summary = period_summary(snapshot, month_start, month_end)
            if month_summary.income_cents > 0:
                rate = (
                    month_summary.income_cents - month_summary.spending_cents
                ) / month_summary.income_cents
                savings_rate_trend.append(round(rate, 3))
            else:
                savings_rate_trend.append(None)

        # Largest category swing first-half vs second-half.
        midpoint = len(months) // 2
        if midpoint >= 1:
            first_half = months[:midpoint]
            second_half = months[midpoint:]
            cat_first: dict[str, int] = defaultdict(int)
            cat_second: dict[str, int] = defaultdict(int)
            cat_names: dict[str, str] = {}

            def _accumulate(month_list: list[tuple[int, int]], bucket: dict[str, int]) -> None:
                for y, m in month_list:
                    ms = date(y, m, 1)
                    me = date(y, m, monthrange(y, m)[1])
                    for t in snapshot.transactions:
                        if t.account_id not in on_budget:
                            continue
                        if not (ms <= t.date <= me):
                            continue
                        if t.payee_id is not None and t.payee_id in internal_transfers:
                            continue
                        if t.category_id is None:
                            continue
                        cat = cat_by_id.get(t.category_id)
                        if cat is None or _is_income_category(cat.name):
                            continue
                        bucket[t.category_id] += -t.amount_cents
                        cat_names[t.category_id] = cat.name

            _accumulate(first_half, cat_first)
            _accumulate(second_half, cat_second)

            swing_id, swing_delta = None, 0
            for cat_id in set(cat_first) | set(cat_second):
                delta = cat_second.get(cat_id, 0) - cat_first.get(cat_id, 0)
                if abs(delta) > abs(swing_delta):
                    swing_id, swing_delta = cat_id, delta
            largest_swing = (
                YearInMoneyTopCategory(
                    category_id=swing_id,
                    category_name=cat_names.get(swing_id, "Uncategorized"),
                    net_spend_cents=swing_delta,
                )
                if swing_id is not None
                else None
            )
        else:
            largest_swing = None

        title_period = "Your year in money" if kind == "annual" else "Your quarter in money"
        title = f"{title_period}: {label}"
        savings_rate = (
            (summary.income_cents - summary.spending_cents) / summary.income_cents
            if summary.income_cents > 0
            else None
        )

        income_d = summary.income_cents / 100
        spend_d = summary.spending_cents / 100
        net_d = summary.net_income_cents / 100
        narrative_pieces: list[str] = [
            f"Across {label}, income totaled ${income_d:,.0f} and spending "
            f"totaled ${spend_d:,.0f}. The difference: ${net_d:,.0f}.",
        ]
        if top_categories:
            top_cat = top_categories[0]
            narrative_pieces.append(
                f"{top_cat.category_name} was the largest spending category at "
                f"${top_cat.net_spend_cents / 100:,.0f}."
            )
        if biggest is not None:
            narrative_pieces.append(
                f"Largest single moment: ${abs(biggest.amount_cents) / 100:,.0f} "
                f"to {biggest.payee_name or 'an uncategorized payee'} on "
                f"{biggest.date.isoformat()}."
            )
        fallback_narrative = " ".join(narrative_pieces)

        data = YearInMoneyData(
            period_label=label,
            period_kind=kind,
            period_start=start,
            period_end=end,
            total_income_cents=summary.income_cents,
            total_spending_cents=summary.spending_cents,
            net_income_cents=summary.net_income_cents,
            savings_rate=round(savings_rate, 3) if savings_rate is not None else None,
            top_categories=top_categories,
            top_payees=top_payees,
            biggest_single=biggest,
            savings_rate_trend=savings_rate_trend,
            largest_category_swing=largest_swing,
            narrative=fallback_narrative,
        )

        enhanced = await enhance_copy(
            anthropic_key=anthropic_key,
            model=anthropic_model,
            fallback_title=title,
            fallback_summary=fallback_narrative,
            card_type=self.card_type,
            payload=data.model_dump(mode="json"),
        )
        if enhanced.used_llm:
            data.narrative = enhanced.summary

        # Bucket the dedup key on (kind, end-month) so the card refreshes
        # at-most-once per month rather than every regenerate, but does
        # roll forward as months pass.
        dedup_key = f"year_in_money:{snapshot.budget_id}:{kind}:{end.strftime('%Y-%m')}"
        return [
            GeneratedInsight(
                dedup_key=dedup_key,
                title=enhanced.title,
                summary=enhanced.summary,
                structured_data=data.model_dump(mode="json"),
                llm_enhanced=enhanced.used_llm,
            )
        ]
