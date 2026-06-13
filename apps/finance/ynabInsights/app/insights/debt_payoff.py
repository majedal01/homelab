"""Debt Payoff generator (v2.6g).

For each open credit-card / line-of-credit account with a negative
balance and observable paydown trend, project payoff date at the
current monthly paydown pace.

YNAB sign convention on credit accounts:
- A new charge appears as a NEGATIVE amount (debit decreases the
  account's balance — you owe more).
- A payment FROM checking to the credit card appears on the credit
  account as a POSITIVE amount (the account's balance moves toward
  zero — you owe less).

So `sum(txns_in_window).amount_cents > 0` means net paydown over the
window: payments outpaced new charges.

We start with a 3-month lookback and fall back to 6 months if the
3-month signal is too thin to be informative (<$20/mo).

Skipped scenarios:
- No credit-card / LoC accounts: no cards.
- Balance is zero or positive: no debt, nothing to pay off.
- Paydown <= 0 (balance growing): not a payoff story.
- Projected months > 120: payoff too far out to be actionable; the
  pace is probably "minimum payments forever" and we don't want to
  surface a discouraging number.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import ClassVar

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.diagnostics import diag
from app.insights.llm import enhance_copy
from app.insights.schemas import DebtPayoffData
from app.snapshot.models import Account, YnabSnapshot

# YNAB account types treated as revolving debt for payoff projection.
DEBT_ACCOUNT_TYPES = frozenset({"creditCard", "lineOfCredit"})

LOOKBACK_MONTHS_DEFAULT = 3
LOOKBACK_MONTHS_FALLBACK = 6
LOOKBACK_FALLBACK_PAYDOWN_FLOOR_CENTS = 2000  # $20/mo
MAX_PROJECTION_MONTHS = 120  # 10 years


@dataclass(frozen=True)
class _Projection:
    account: Account
    monthly_paydown_cents: int
    lookback_months: int


@register_generator
class DebtPayoffGenerator(InsightGenerator):
    card_type: ClassVar[str] = "debt_payoff"
    cadence: ClassVar[str] = "monthly"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        debt_accounts = [
            a
            for a in snapshot.accounts
            if a.type in DEBT_ACCOUNT_TYPES and not a.closed and a.balance_cents < 0
        ]
        diag("debt_payoff", "start", debt_accounts=len(debt_accounts))

        projections: list[_Projection] = []
        rejections: dict[str, int] = {}
        for account in debt_accounts:
            paydown_3mo = _monthly_paydown(snapshot, account.id, today, months=3)
            lookback = LOOKBACK_MONTHS_DEFAULT
            paydown = paydown_3mo
            if paydown < LOOKBACK_FALLBACK_PAYDOWN_FLOOR_CENTS:
                # 3mo signal is thin; widen to 6mo.
                paydown = _monthly_paydown(snapshot, account.id, today, months=6)
                lookback = LOOKBACK_MONTHS_FALLBACK
            if paydown <= 0:
                rejections["non_positive_paydown"] = rejections.get("non_positive_paydown", 0) + 1
                continue
            current_debt = -account.balance_cents
            months_to_payoff = max(round(current_debt / paydown), 1)
            if months_to_payoff > MAX_PROJECTION_MONTHS:
                rejections["projection_over_max"] = rejections.get("projection_over_max", 0) + 1
                continue
            projections.append(
                _Projection(
                    account=account,
                    monthly_paydown_cents=paydown,
                    lookback_months=lookback,
                )
            )

        for reason, count in rejections.items():
            diag("debt_payoff", "rejected", reason=reason, count=count)

        outputs: list[GeneratedInsight] = []
        for projection in projections:
            account = projection.account
            current_debt = -account.balance_cents
            months_to_payoff = max(round(current_debt / projection.monthly_paydown_cents), 1)
            payoff_date = today + timedelta(days=months_to_payoff * 30)

            data = DebtPayoffData(
                account_id=account.id,
                account_name=account.name,
                account_type=account.type,
                current_debt_cents=current_debt,
                avg_monthly_paydown_cents=projection.monthly_paydown_cents,
                lookback_months=projection.lookback_months,
                projected_months_to_payoff=months_to_payoff,
                projected_payoff_date=payoff_date,
            )

            debt_dollars = current_debt / 100
            paydown_dollars = projection.monthly_paydown_cents / 100
            fallback_title = (
                f"{account.name}: ${debt_dollars:,.0f} debt, "
                f"paid off by {payoff_date.strftime('%b %Y')}"
            )
            fallback_summary = (
                f"At your last {projection.lookback_months}-month pace of "
                f"${paydown_dollars:,.0f}/mo, "
                f"{account.name} would be paid off in {months_to_payoff} months."
            )

            enhanced = await enhance_copy(
                anthropic_key=anthropic_key,
                model=anthropic_model,
                fallback_title=fallback_title,
                fallback_summary=fallback_summary,
                card_type=self.card_type,
                payload=data.model_dump(mode="json"),
            )

            outputs.append(
                GeneratedInsight(
                    dedup_key=(f"debt_payoff:{account.id}:{today.strftime('%Y-%m')}"),
                    title=enhanced.title,
                    summary=enhanced.summary,
                    structured_data=data.model_dump(mode="json"),
                    llm_enhanced=enhanced.used_llm,
                )
            )

        diag("debt_payoff", "finished", insights_emitted=len(outputs))
        return outputs


def _monthly_paydown(
    snapshot: YnabSnapshot,
    account_id: str,
    today: date,
    *,
    months: int,
) -> int:
    """Sum txns in account over the last `months` calendar months,
    divide by months. Positive result = paying down net of new charges.

    YNAB credit-card sign: payments appear positive on the credit account
    (balance becomes less negative), charges appear negative. Summing
    txn amounts directly gives the net balance delta over the window."""
    window_start = today - timedelta(days=30 * months)
    total = 0
    for t in snapshot.transactions:
        if t.account_id != account_id:
            continue
        if not (window_start <= t.date <= today):
            continue
        total += t.amount_cents
    return total // max(months, 1)
