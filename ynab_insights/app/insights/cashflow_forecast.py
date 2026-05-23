"""Cashflow Forecast generator.

Projects net liquidity 30/60/90 days out from the mean daily net cashflow
observed over the trailing 90 days. Dedup key is bucketed by ISO week so
the daily-cadence scheduler refreshes the same card seven days in a row
instead of producing a new one each day.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from datetime import date, timedelta
from typing import ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import (
    CashflowForecastData,
    CategoryRate,
)
from app.models import Account
from app.services.queries import list_transactions

LOOKBACK_DAYS = 90
TOP_CATEGORIES = 5


@register_generator
class CashflowForecastGenerator(InsightGenerator):
    card_type: ClassVar[str] = "cashflow_forecast"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        session: AsyncSession,
        settings: Settings,
        budget_id: str,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        start = today - timedelta(days=LOOKBACK_DAYS)

        accounts = (
            await session.execute(
                select(Account).where(
                    Account.budget_id == budget_id,
                    Account.closed.is_(False),
                    Account.on_budget.is_(True),
                )
            )
        ).scalars().all()
        starting_balance_cents = sum(a.balance_cents for a in accounts)

        txns = await list_transactions(
            session,
            budget_id=budget_id,
            date_from=start,
            date_to=today,
            limit=500,
        )
        # Exclude transfers from cashflow; they're internal moves of money.
        non_transfer = [
            t
            for t in txns
            if not (t.payee is not None and t.payee.transfer_account_id is not None)
        ]
        if not non_transfer:
            return []

        net_cents = sum(t.amount_cents for t in non_transfer)
        daily_net = round(net_cents / LOOKBACK_DAYS)

        projected_30 = starting_balance_cents + daily_net * 30
        projected_60 = starting_balance_cents + daily_net * 60
        projected_90 = starting_balance_cents + daily_net * 90

        # Top spending categories by aggregate outflow over the window.
        category_totals: dict[str | None, int] = defaultdict(int)
        category_names: dict[str | None, str] = {None: "Uncategorized"}
        for t in non_transfer:
            if t.amount_cents >= 0:
                continue
            category_totals[t.category_id] += -t.amount_cents
            if t.category_id is not None and t.category is not None:
                category_names[t.category_id] = t.category.name

        top = sorted(category_totals.items(), key=lambda kv: kv[1], reverse=True)[
            :TOP_CATEGORIES
        ]
        top_rates = [
            CategoryRate(
                category_id=cat_id,
                category_name=category_names.get(cat_id, "Uncategorized"),
                monthly_average_cents=round(total / LOOKBACK_DAYS * 30),
            )
            for cat_id, total in top
        ]

        data = CashflowForecastData(
            starting_balance_cents=starting_balance_cents,
            daily_net_cents=daily_net,
            projected_30d_cents=projected_30,
            projected_60d_cents=projected_60,
            projected_90d_cents=projected_90,
            lookback_days=LOOKBACK_DAYS,
            top_spending_categories=top_rates,
        )

        projected_dollars = projected_90 / 100
        starting_dollars = starting_balance_cents / 100
        direction = "grow to" if projected_90 >= starting_balance_cents else "drop to"
        fallback_title = f"Projected 90-day balance: ${projected_dollars:,.0f}"
        fallback_summary = (
            f"At your last 90 days' pace, balances would {direction} "
            f"${projected_dollars:,.0f} from today's ${starting_dollars:,.0f}."
        )

        enhanced = await enhance_copy(
            settings=settings,
            fallback_title=fallback_title,
            fallback_summary=fallback_summary,
            card_type=self.card_type,
            payload=data.model_dump(mode="json"),
        )

        iso = today.isocalendar()
        dedup_key = f"forecast:{budget_id}:{iso.year}-W{iso.week:02d}"
        return [
            GeneratedInsight(
                dedup_key=dedup_key,
                title=enhanced.title,
                summary=enhanced.summary,
                structured_data=data.model_dump(mode="json"),
                llm_enhanced=enhanced.used_llm,
            )
        ]
