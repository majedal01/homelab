"""Hand-written demo insights, one per card type.

These ship as `llm_enhanced=False` so the existing card UI renders them
exactly the same way it would render a deterministic-fallback insight
from a real session that didn't have an LLM key. The numbers reference
the deterministic demo snapshot so the cards stay internally consistent.

Adding a new card type to the registry? Add a builder here too so the
demo doesn't gain a hole.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from app.insights.base import Insight
from app.snapshot.models import YnabSnapshot


def build_demo_insights(snapshot: YnabSnapshot) -> list[Insight]:
    """Return one Insight per card type, deterministic for the demo snapshot."""
    today = snapshot.fetched_at.date()
    now = datetime.now(UTC)
    return [
        _subscription_audit(today, now),
        _spending_anomaly(today, now),
        _cashflow_forecast(snapshot.budget_id, today, now),
        _goal_trajectory(today, now),
        _category_drift(today, now),
        _year_in_money(snapshot.budget_id, today, now),
    ]


# --- per-card builders ------------------------------------------------------


def _subscription_audit(today: date, now: datetime) -> Insight:
    payee = "Anthropic"
    occurrences = _last_n_first_of_month(today, 6)
    return Insight(
        id=1,
        budget_id="demo-budget",
        card_type="subscription_audit",
        dedup_key="subscription:p-claude:2000:monthly",
        title=f"$20.00/mo to {payee}",
        summary=(f"Recurring monthly charge of $20.00 to {payee}. $20.00/month, $240.00/year."),
        structured_data={
            "card_type": "subscription_audit",
            "payee_id": "p-claude",
            "payee_name": payee,
            "cadence": "monthly",
            "amount_cents": 2000,
            "monthly_cost_cents": 2000,
            "annual_cost_cents": 24000,
            "occurrences": [
                {
                    "id": f"t-clde-{d.isoformat()}",
                    "date": d.isoformat(),
                    "amount_cents": -2000,
                    "payee_name": payee,
                    "memo": None,
                }
                for d in occurrences
            ],
            "first_seen": occurrences[0].isoformat(),
            "last_seen": occurrences[-1].isoformat(),
        },
        generated_at=now,
        refreshed_at=now,
        llm_enhanced=False,
    )


def _spending_anomaly(today: date, now: datetime) -> Insight:
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    iso = week_start.isocalendar()
    return Insight(
        id=2,
        budget_id="demo-budget",
        card_type="spending_anomaly",
        dedup_key=f"anomaly:cat-groceries:{iso.year}-W{iso.week:02d}",
        title="Groceries spending is above usual",
        summary=("You spent $310 on Groceries this week, 169% above your 12-week average of $115."),
        structured_data={
            "card_type": "spending_anomaly",
            "category_id": "cat-groceries",
            "category_name": "Groceries",
            "cycle": "weekly",
            "period_start": week_start.isoformat(),
            "period_end": week_end.isoformat(),
            "current_period_spend_cents": 31000,
            "baseline_mean_cents": 11500,
            "baseline_stdev_cents": 1850,
            "z_score": 10.54,
            "deviation_ratio": 1.69,
            "top_transactions": [
                {
                    "id": f"t-gr-{week_start.isoformat()}",
                    "date": week_start.isoformat(),
                    "amount_cents": -31000,
                    "payee_name": "Whole Foods",
                },
            ],
        },
        generated_at=now,
        refreshed_at=now,
        llm_enhanced=False,
    )


def _cashflow_forecast(budget_id: str, today: date, now: datetime) -> Insight:
    iso = today.isocalendar()
    return Insight(
        id=3,
        budget_id=budget_id,
        card_type="cashflow_forecast",
        dedup_key=f"forecast:{budget_id}:{iso.year}-W{iso.week:02d}",
        title="Projected 90-day cash: $27,700",
        summary=(
            "At your last 90 days' pace, cash balances would grow to $27,700 from today's $22,755."
        ),
        structured_data={
            "card_type": "cashflow_forecast",
            "starting_balance_cents": 22_755_00,
            "credit_card_debt_cents": 1_286_00,
            "daily_net_cents": 5500,
            "projected_30d_cents": 24_405_00,
            "projected_60d_cents": 26_055_00,
            "projected_90d_cents": 27_705_00,
            "lookback_days": 90,
            "lookback_income_cents": 14_400_00,
            "lookback_spending_cents": 9_450_00,
            "top_spending_categories": [
                {
                    "category_id": "cat-rent",
                    "category_name": "Rent",
                    "monthly_average_cents": 1_650_00,
                },
                {
                    "category_id": "cat-groceries",
                    "category_name": "Groceries",
                    "monthly_average_cents": 540_00,
                },
                {
                    "category_id": "cat-dining",
                    "category_name": "Dining out",
                    "monthly_average_cents": 305_00,
                },
                {
                    "category_id": "cat-travel",
                    "category_name": "Travel",
                    "monthly_average_cents": 230_00,
                },
                {
                    "category_id": "cat-coffee",
                    "category_name": "Coffee",
                    "monthly_average_cents": 85_00,
                },
            ],
        },
        generated_at=now,
        refreshed_at=now,
        llm_enhanced=False,
    )


def _goal_trajectory(today: date, now: datetime) -> Insight:
    target_month = today.replace(day=1) + timedelta(days=210)
    projected = today.replace(day=1) + timedelta(days=150)
    return Insight(
        id=4,
        budget_id="demo-budget",
        card_type="goal_trajectory",
        dedup_key=f"goal:cat-vacation:{today.strftime('%Y-%m')}",
        title="Vacation Fund: $2,100 to go of $5,000",
        summary=(
            "You're 58% of the way to Vacation Fund "
            "($5,000), on pace for your "
            f"{target_month.strftime('%b %Y')} target."
        ),
        structured_data={
            "card_type": "goal_trajectory",
            "category_id": "cat-vacation",
            "category_name": "Vacation Fund",
            "goal_type": "TBD",
            "target_cents": 5_000_00,
            "progress_cents": 2_900_00,
            "remaining_cents": 2_100_00,
            "percent_complete": 58,
            "current_monthly_contribution_cents": 300_00,
            "target_date": target_month.isoformat(),
            "projected_completion_date": projected.isoformat(),
            "months_to_target": 5,
            "on_track": True,
        },
        generated_at=now,
        refreshed_at=now,
        llm_enhanced=False,
    )


def _category_drift(today: date, now: datetime) -> Insight:
    # 12 monthly nets, oldest first, positive = spend. The trailing quarter
    # averages $310/mo, prior three quarters average $230/mo (~35% up).
    nets = [
        225_00,
        235_00,
        230_00,
        225_00,
        240_00,
        220_00,
        235_00,
        230_00,
        0,
        305_00,
        315_00,
        310_00,
    ]
    return Insight(
        id=5,
        budget_id="demo-budget",
        card_type="category_drift",
        dedup_key=f"drift:cat-dining:{today.strftime('%Y-%m')}",
        title="Dining out is up 35% vs the prior year",
        summary=(
            "Dining out averaged $80/mo more in the last quarter than the three quarters before it."
        ),
        structured_data={
            "card_type": "category_drift",
            "category_id": "cat-dining",
            "category_name": "Dining out",
            "comparison_kind": "quarter_over_quarter",
            "trailing_quarter_avg_cents": 310_00,
            "prior_three_quarters_avg_cents": 230_00,
            "drift_pct": 0.348,
            "drift_cents_per_month": 80_00,
            "direction": "up",
            "monthly_nets_cents": nets,
        },
        generated_at=now,
        refreshed_at=now,
        llm_enhanced=False,
    )


def _year_in_money(budget_id: str, today: date, now: datetime) -> Insight:
    # Use last completed calendar quarter so the card has period boundaries
    # that read naturally regardless of when the demo loads.
    qm = ((today.month - 1) // 3) * 3  # last completed quarter end month (0=12 fallback below)
    if qm == 0:
        year = today.year - 1
        start = date(year, 10, 1)
        end = date(year, 12, 31)
        label = f"{year}-Q4"
    else:
        start_month = qm - 2
        start = date(today.year, start_month, 1)
        # Last day of the previous-quarter end month.
        next_month = qm + 1
        end_year = today.year + (1 if next_month > 12 else 0)
        end_month = (next_month - 1) % 12 + 1
        end = date(end_year, end_month, 1) - timedelta(days=1)
        label = f"{today.year}-Q{qm // 3}"

    return Insight(
        id=6,
        budget_id=budget_id,
        card_type="year_in_money",
        dedup_key=f"year_in_money:{budget_id}:{label}",
        title=f"Your quarter in money, {label}",
        summary=(
            f"Across {label}, income totaled $14,400 and spending totaled $9,450. "
            "The difference: $4,950. Rent was the largest spending category at $4,950. "
            "Largest single moment: $812 to Kaiser Permanente."
        ),
        structured_data={
            "card_type": "year_in_money",
            "period_label": label,
            "period_kind": "quarterly",
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "total_income_cents": 14_400_00,
            "total_spending_cents": 9_450_00,
            "net_income_cents": 4_950_00,
            "savings_rate": 0.344,
            "top_categories": [
                {"category_id": "cat-rent", "category_name": "Rent", "net_spend_cents": 4_950_00},
                {
                    "category_id": "cat-groceries",
                    "category_name": "Groceries",
                    "net_spend_cents": 1_620_00,
                },
                {
                    "category_id": "cat-dining",
                    "category_name": "Dining out",
                    "net_spend_cents": 915_00,
                },
            ],
            "top_payees": [
                {
                    "payee_id": "p-landlord",
                    "payee_name": "Greystar Apartments",
                    "transaction_count": 3,
                    "amount_cents": 4_950_00,
                },
                {
                    "payee_id": "p-wholefoods",
                    "payee_name": "Whole Foods",
                    "transaction_count": 8,
                    "amount_cents": 1_020_00,
                },
                {
                    "payee_id": "p-kaiser",
                    "payee_name": "Kaiser Permanente",
                    "transaction_count": 1,
                    "amount_cents": 812_00,
                },
            ],
            "biggest_single": {
                "transaction_id": "t-dr-ann",
                "date": (today - timedelta(days=50)).isoformat(),
                "amount_cents": -812_00,
                "payee_name": "Kaiser Permanente",
                "category_name": "Health",
            },
            "savings_rate_trend": [0.31, 0.35, 0.37],
            "largest_category_swing": {
                "category_id": "cat-dining",
                "category_name": "Dining out",
                "net_spend_cents": 240_00,
            },
            "narrative": (
                f"Across {label}, income totaled $14,400 and spending totaled $9,450. "
                "The difference: $4,950. Rent was the largest spending category at $4,950. "
                "Largest single moment: $812 to Kaiser Permanente."
            ),
        },
        generated_at=now,
        refreshed_at=now,
        llm_enhanced=False,
    )


# --- helpers ----------------------------------------------------------------


def _last_n_first_of_month(today: date, n: int) -> list[date]:
    out: list[date] = []
    y, m = today.year, today.month
    for _ in range(n):
        if m == 0:
            m = 12
            y -= 1
        out.append(date(y, m, 1))
        m -= 1
    return list(reversed(out))
