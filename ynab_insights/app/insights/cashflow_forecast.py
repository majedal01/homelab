"""Cashflow Forecast generator.

Projects net liquidity 30/60/90 days out from the mean daily net cashflow
observed over the trailing 90 days. Scoped to on-budget accounts.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import ClassVar

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import CashflowForecastData, CategoryRate
from app.snapshot.models import YnabSnapshot
from app.snapshot.queries import (
    _internal_transfer_payee_ids,
    _is_income_category,
    spending_by_category,
    starting_balance_cents,
    transactions_in_range,
)

LOOKBACK_DAYS = 90
TOP_CATEGORIES = 5


@register_generator
class CashflowForecastGenerator(InsightGenerator):
    card_type: ClassVar[str] = "cashflow_forecast"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        start = today - timedelta(days=LOOKBACK_DAYS)

        balance = starting_balance_cents(snapshot)
        if balance == 0 and not any(a.on_budget and not a.closed for a in snapshot.accounts):
            return []

        on_budget = {a.id for a in snapshot.accounts if a.on_budget}
        cat_by_id = snapshot.category_by_id()
        internal_transfers = _internal_transfer_payee_ids(snapshot)

        income_cents = 0
        spending_cents = 0
        for t in transactions_in_range(snapshot, start, today):
            if t.account_id not in on_budget:
                continue
            if t.payee_id is not None and t.payee_id in internal_transfers:
                continue
            cat = cat_by_id.get(t.category_id) if t.category_id else None
            cat_name = cat.name if cat else None
            if t.amount_cents > 0 and (t.category_id is None or _is_income_category(cat_name)):
                income_cents += t.amount_cents
                continue
            if t.category_id is None:
                continue
            if _is_income_category(cat_name):
                continue
            spending_cents += -t.amount_cents  # positive

        net_cents = income_cents - spending_cents
        daily_net = round(net_cents / LOOKBACK_DAYS)

        projected_30 = balance + daily_net * 30
        projected_60 = balance + daily_net * 60
        projected_90 = balance + daily_net * 90

        category_spend = spending_by_category(snapshot, start, today)
        top_rates = [
            CategoryRate(
                category_id=row.category_id,
                category_name=row.category_name or "Uncategorized",
                monthly_average_cents=round(-row.spent_cents / LOOKBACK_DAYS * 30),
            )
            for row in category_spend[:TOP_CATEGORIES]
        ]

        data = CashflowForecastData(
            starting_balance_cents=balance,
            daily_net_cents=daily_net,
            projected_30d_cents=projected_30,
            projected_60d_cents=projected_60,
            projected_90d_cents=projected_90,
            lookback_days=LOOKBACK_DAYS,
            lookback_income_cents=income_cents,
            lookback_spending_cents=spending_cents,
            top_spending_categories=top_rates,
        )

        projected_dollars = projected_90 / 100
        starting_dollars = balance / 100
        direction = "grow to" if projected_90 >= balance else "drop to"
        fallback_title = f"Projected 90-day balance: ${projected_dollars:,.0f}"
        fallback_summary = (
            f"At your last 90 days' pace, balances would {direction} "
            f"${projected_dollars:,.0f} from today's ${starting_dollars:,.0f}."
        )

        enhanced = await enhance_copy(
            anthropic_key=anthropic_key,
            model=anthropic_model,
            fallback_title=fallback_title,
            fallback_summary=fallback_summary,
            card_type=self.card_type,
            payload=data.model_dump(mode="json"),
        )

        iso = today.isocalendar()
        dedup_key = f"forecast:{snapshot.budget_id}:{iso.year}-W{iso.week:02d}"
        return [
            GeneratedInsight(
                dedup_key=dedup_key,
                title=enhanced.title,
                summary=enhanced.summary,
                structured_data=data.model_dump(mode="json"),
                llm_enhanced=enhanced.used_llm,
            )
        ]
