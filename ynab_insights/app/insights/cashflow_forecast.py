"""Cashflow Forecast generator (v2.6f).

Projects available cash 30/60/90 days out from the mean daily net
cashflow observed over the trailing 90 days. Scoped to cash accounts
(checking, savings, cash) only — credit-card balances are reported
separately as `credit_card_debt_cents` rather than netted against cash.

The v2.4 headline number subtracted credit-card balances, which made
revolving debt look like a hole in the user's cash position. A user
with $3k checking and $5k owed on a credit card is not -$2k poorer
than today; they have $3k cash and a $5k debt paid down over time.
The two facts are surfaced separately.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import ClassVar

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.diagnostics import diag
from app.insights.llm import enhance_copy
from app.insights.schemas import CashflowForecastData, CategoryRate
from app.snapshot.models import YnabSnapshot
from app.snapshot.queries import (
    _internal_transfer_payee_ids,
    _is_income_category,
    cash_balance_cents,
    credit_card_debt_cents,
    spending_by_category,
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

        balance = cash_balance_cents(snapshot)
        credit_debt = credit_card_debt_cents(snapshot)
        diag(
            "cashflow_forecast",
            "balances",
            cash_cents=balance,
            credit_debt_cents=credit_debt,
        )
        if balance == 0 and not any(a.on_budget and not a.closed for a in snapshot.accounts):
            diag("cashflow_forecast", "skipped", reason="no_active_accounts")
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
            credit_card_debt_cents=credit_debt,
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
        fallback_title = f"Projected 90-day cash: ${projected_dollars:,.0f}"
        fallback_summary = (
            f"At your last 90 days' pace, cash balances would {direction} "
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

        diag(
            "cashflow_forecast",
            "projection",
            daily_net_cents=daily_net,
            projected_90d_cents=projected_90,
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
