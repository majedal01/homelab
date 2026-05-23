"""Year in Money generator.

Annual (Jan 1) and quarterly (Apr 1 / Jul 1 / Oct 1) retrospective card.
Deterministic Python assembles the stats; the LLM writes the narrative.
Narrative falls back to a deterministic paragraph if the LLM call is
unavailable.

Heuristic rationale lives in `docs/ynab-insights.md` under "Card type:
Year in Money".
"""

from __future__ import annotations

import logging
from calendar import monthrange
from collections import defaultdict
from collections.abc import Sequence
from datetime import date
from typing import ClassVar, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import Settings
from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import (
    YearInMoneyBiggestSingle,
    YearInMoneyData,
    YearInMoneyTopCategory,
    YearInMoneyTopPayee,
)
from app.models import Account, Category, Payee, Transaction
from app.services.queries import (
    INCOME_CATEGORY_NAMES,
    _exclude_transfers,
    period_summary,
)

logger = logging.getLogger(__name__)


def _period_bounds(today: date) -> tuple[Literal["annual", "quarterly"], date, date, str] | None:
    """Return (kind, start, end_inclusive, label) for the period to publish.

    Annual on Jan 1 (looking at the just-finished year). Quarterly on the
    first of Apr/Jul/Oct (looking at the just-finished quarter). On other
    days returns None so the generator is a no-op (scheduler still records
    a successful run with 0 outputs).
    """
    if today.month == 1 and today.day == 1:
        year = today.year - 1
        return (
            "annual",
            date(year, 1, 1),
            date(year, 12, 31),
            str(year),
        )
    if today.day == 1 and today.month in (4, 7, 10):
        month = today.month - 1
        quarter = month // 3  # 1-indexed (Q1, Q2, Q3)
        year = today.year
        if today.month == 1:
            year -= 1
        start_month = month - 2
        start = date(year, start_month, 1)
        end = date(year, month, monthrange(year, month)[1])
        return ("quarterly", start, end, f"{year}-Q{quarter}")
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
        session: AsyncSession,
        settings: Settings,
        budget_id: str,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        bounds = _period_bounds(today)
        if bounds is None:
            return []
        kind, start, end, label = bounds

        summary = await period_summary(session, budget_id, start, end)
        if summary.transaction_count == 0:
            # Not enough data for this period — skip with a clean no-op so
            # the scheduler still records an "ok" run.
            return []

        # Top three categories by net spend.
        top_categories = [
            YearInMoneyTopCategory(
                category_id=row.category_id,
                category_name=row.category_name or "Uncategorized",
                net_spend_cents=-row.net_cents,
            )
            for row in summary.by_category
            if row.net_cents < 0
        ][:3]

        # Top five payees by amount × frequency (combined score = total
        # absolute spend on them).
        payee_stmt = _exclude_transfers(
            select(
                Payee.id,
                Payee.name,
                func.count().label("txn_count"),
                func.coalesce(func.sum(-Transaction.amount_cents), 0).label("total"),
            )
            .select_from(Transaction)
            .outerjoin(Payee, Payee.id == Transaction.payee_id)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.date >= start,
                Transaction.date <= end,
                Transaction.amount_cents < 0,
                Transaction.category_id.is_not(None),
                Category.name.notin_(INCOME_CATEGORY_NAMES),
                Account.on_budget.is_(True),
            )
            .group_by(Payee.id, Payee.name)
            .order_by(func.sum(-Transaction.amount_cents).desc())
            .limit(5)
        )
        payee_rows = (await session.execute(payee_stmt)).all()
        top_payees = [
            YearInMoneyTopPayee(
                payee_id=row.id,
                payee_name=row.name or "Uncategorized payee",
                transaction_count=int(row.txn_count),
                amount_cents=int(row.total),
            )
            for row in payee_rows
        ]

        # Biggest single transaction (most negative amount).
        biggest_stmt = _exclude_transfers(
            select(Transaction)
            .options(
                joinedload(Transaction.category),
                joinedload(Transaction.payee),
            )
            .join(Account, Account.id == Transaction.account_id)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.date >= start,
                Transaction.date <= end,
                Account.on_budget.is_(True),
                Transaction.category_id.is_not(None),
                Category.name.notin_(INCOME_CATEGORY_NAMES),
                or_(
                    Transaction.amount_cents < 0,
                    Transaction.amount_cents > 0,
                ),
            )
            .order_by(Transaction.amount_cents)  # most-negative first
            .limit(1)
        )
        biggest_row = (await session.execute(biggest_stmt)).scalars().first()
        biggest: YearInMoneyBiggestSingle | None = None
        if biggest_row is not None and biggest_row.amount_cents < 0:
            biggest = YearInMoneyBiggestSingle(
                transaction_id=biggest_row.id,
                date=biggest_row.date,
                amount_cents=biggest_row.amount_cents,
                payee_name=biggest_row.payee.name if biggest_row.payee else None,
                category_name=biggest_row.category.name if biggest_row.category else None,
            )

        # Monthly savings-rate series.
        months = _months_in_window(start, end)
        savings_rate_trend: list[float | None] = []
        for y, m in months:
            month_start = date(y, m, 1)
            month_end = date(y, m, monthrange(y, m)[1])
            month_summary = await period_summary(session, budget_id, month_start, month_end)
            if month_summary.income_cents > 0:
                rate = (
                    month_summary.income_cents - month_summary.spending_cents
                ) / month_summary.income_cents
                savings_rate_trend.append(round(rate, 3))
            else:
                savings_rate_trend.append(None)

        # Largest single category swing — same shape as Category Drift but
        # at period granularity. We compare each category's net in the
        # second half to its net in the first half. Quick + good enough.
        midpoint = len(months) // 2
        if midpoint >= 1:
            first_half = months[:midpoint]
            second_half = months[midpoint:]
            cat_first: dict[str, int] = defaultdict(int)
            cat_second: dict[str, int] = defaultdict(int)
            cat_names: dict[str, str] = {}
            for (y, m), bucket, label_bucket in (
                *[(ym, cat_first, "first") for ym in first_half],
                *[(ym, cat_second, "second") for ym in second_half],
            ):
                month_start = date(y, m, 1)
                month_end = date(y, m, monthrange(y, m)[1])
                cat_stmt = _exclude_transfers(
                    select(
                        Category.id,
                        Category.name,
                        func.coalesce(func.sum(-Transaction.amount_cents), 0).label("net"),
                    )
                    .select_from(Transaction)
                    .outerjoin(Category, Category.id == Transaction.category_id)
                    .join(Account, Account.id == Transaction.account_id)
                    .where(
                        Transaction.budget_id == budget_id,
                        Transaction.date >= month_start,
                        Transaction.date <= month_end,
                        Transaction.category_id.is_not(None),
                        Category.name.notin_(INCOME_CATEGORY_NAMES),
                        Account.on_budget.is_(True),
                    )
                    .group_by(Category.id, Category.name)
                )
                del label_bucket
                for row in (await session.execute(cat_stmt)).all():
                    bucket[row.id] += int(row.net)
                    cat_names[row.id] = row.name
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
        title = f"{title_period}, {label}"
        savings_rate = (
            (summary.income_cents - summary.spending_cents) / summary.income_cents
            if summary.income_cents > 0
            else None
        )

        # Deterministic fallback narrative — restrained, observed.
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

        # Enhanced copy: title is short; the LLM gets the full payload and
        # writes the narrative paragraph. If LLM unavailable, the
        # deterministic narrative above stays in place.
        enhanced = await enhance_copy(
            settings=settings,
            fallback_title=title,
            fallback_summary=fallback_narrative,
            card_type=self.card_type,
            payload=data.model_dump(mode="json"),
        )
        if enhanced.used_llm:
            data.narrative = enhanced.summary

        dedup_key = f"year_in_money:{budget_id}:{label}"
        return [
            GeneratedInsight(
                dedup_key=dedup_key,
                title=enhanced.title,
                summary=enhanced.summary,
                structured_data=data.model_dump(mode="json"),
                llm_enhanced=enhanced.used_llm,
            )
        ]
