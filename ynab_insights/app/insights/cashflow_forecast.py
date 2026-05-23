"""Cashflow Forecast generator.

Projects net liquidity 30/60/90 days out from the mean daily net cashflow
observed over the trailing 90 days. Scoped to on-budget accounts so
tracking-account flows (investment buys/sells, asset balance corrections)
don't skew the projection. Dedup key is bucketed by ISO week so the
daily-cadence scheduler refreshes the same card seven days in a row
instead of producing a new one each day.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import ClassVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import (
    CashflowForecastData,
    CategoryRate,
)
from app.models import Account, Transaction
from app.services.queries import _exclude_transfers, spending_by_category

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
            (
                await session.execute(
                    select(Account).where(
                        Account.budget_id == budget_id,
                        Account.closed.is_(False),
                        Account.on_budget.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not accounts:
            return []
        starting_balance_cents = sum(a.balance_cents for a in accounts)

        # Aggregate net cashflow in SQL: on-budget only, transfers excluded.
        # Avoids the /transactions limit cap that would silently drop the
        # oldest days when a user has more than ~500 transactions in 90 days,
        # and avoids pulling tracking-account flows that would distort the
        # projection (e.g. a $-10k investment buy isn't real spending).
        net_stmt = _exclude_transfers(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0))
            .select_from(Transaction)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                Transaction.budget_id == budget_id,
                Transaction.date >= start,
                Transaction.date <= today,
                Account.on_budget.is_(True),
                Account.closed.is_(False),
            )
        )
        net_cents = int((await session.execute(net_stmt)).scalar_one())
        daily_net = round(net_cents / LOOKBACK_DAYS)

        projected_30 = starting_balance_cents + daily_net * 30
        projected_60 = starting_balance_cents + daily_net * 60
        projected_90 = starting_balance_cents + daily_net * 90

        # Top categories by NET spend (inflows in the same category cancel
        # outflows — reimbursable expenses, etc). Reuses the shared service
        # so the slider math the frontend exposes lines up with what the
        # agent sees and with the spending donut on the dashboard.
        category_spend = await spending_by_category(session, budget_id, start, today)
        top_rates = [
            CategoryRate(
                category_id=row.category_id,
                category_name=row.category_name or "Uncategorized",
                monthly_average_cents=round(-row.spent_cents / LOOKBACK_DAYS * 30),
            )
            for row in category_spend[:TOP_CATEGORIES]
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
