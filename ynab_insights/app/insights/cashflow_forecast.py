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

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import (
    CashflowForecastData,
    CategoryRate,
)
from app.models import Account, Category, Transaction
from app.services.queries import INCOME_CATEGORY_NAME, _exclude_transfers, spending_by_category

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

        # Aggregate income and spending separately so the detail card can
        # show the user the inputs to the projection. YNAB semantics:
        # - Income = positive amounts in null category (Ready to Assign)
        # - Spending = sum of amounts on categorized rows (refunds reduce
        #   spending naturally)
        # Both restricted to on-budget non-transfer rows to keep
        # tracking-account flows (investment buys, etc.) from skewing the
        # daily net.
        base_filter = (
            Transaction.budget_id == budget_id,
            Transaction.date >= start,
            Transaction.date <= today,
            Account.on_budget.is_(True),
            Account.closed.is_(False),
        )
        income_stmt = _exclude_transfers(
            select(func.coalesce(func.sum(Transaction.amount_cents), 0))
            .select_from(Transaction)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                *base_filter,
                Transaction.amount_cents > 0,
                or_(
                    Transaction.category_id.is_(None),
                    Category.name == INCOME_CATEGORY_NAME,
                ),
            )
        )
        spending_stmt = _exclude_transfers(
            select(func.coalesce(func.sum(-Transaction.amount_cents), 0))
            .select_from(Transaction)
            .outerjoin(Category, Category.id == Transaction.category_id)
            .join(Account, Account.id == Transaction.account_id)
            .where(
                *base_filter,
                Transaction.category_id.is_not(None),
                Category.name != INCOME_CATEGORY_NAME,
            )
        )
        lookback_income_cents = int((await session.execute(income_stmt)).scalar_one())
        lookback_spending_cents = int((await session.execute(spending_stmt)).scalar_one())
        net_cents = lookback_income_cents - lookback_spending_cents
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
            lookback_income_cents=lookback_income_cents,
            lookback_spending_cents=lookback_spending_cents,
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
