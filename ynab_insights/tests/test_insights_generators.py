"""Generator-level tests.

These tests cover the deterministic detection paths of each card type and
the orchestrator's dedup + InsightRun behavior. LLM enhancement is gated
on `anthropic_api_key`, which is unset in tests, so the fallback copy is
exercised throughout.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.insights import all_generators, execute_generator
from app.insights.base import GeneratedInsight, InsightGenerator
from app.insights.cashflow_forecast import CashflowForecastGenerator
from app.insights.category_drift import CategoryDriftGenerator
from app.insights.goal_trajectory import GoalTrajectoryGenerator
from app.insights.spending_anomaly import SpendingAnomalyGenerator
from app.insights.subscription_audit import SubscriptionAuditGenerator
from app.models import (
    Account,
    Budget,
    Category,
    Insight,
    InsightRun,
    Payee,
    Transaction,
)


@pytest_asyncio.fixture
async def budget(db_session: AsyncSession) -> Budget:
    b = Budget(
        id="b-1",
        name="Main",
        currency="USD",
        last_modified_on=datetime(2026, 5, 1, tzinfo=UTC),
    )
    db_session.add(b)
    await db_session.commit()
    return b


def _today() -> date:
    return date.today()


async def test_all_generators_registered() -> None:
    types = {g.card_type for g in all_generators()}
    assert types == {
        "subscription_audit",
        "spending_anomaly",
        "cashflow_forecast",
        "goal_trajectory",
        "category_drift",
        "year_in_money",
    }


async def test_subscription_audit_detects_monthly_cluster(
    db_session: AsyncSession, budget: Budget
) -> None:
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    db_session.add(Payee(id="p-netflix", budget_id="b-1", name="Netflix"))
    today = _today()
    # Three monthly charges over the last 90 days.
    for i, days_ago in enumerate([2, 32, 62]):
        db_session.add(
            Transaction(
                id=f"t-sub-{i}",
                budget_id="b-1",
                account_id="a-1",
                payee_id="p-netflix",
                category_id=None,
                date=today - timedelta(days=days_ago),
                amount_cents=-1599,
                memo=None,
                cleared="cleared",
                approved=True,
            )
        )
    await db_session.commit()

    outputs = await SubscriptionAuditGenerator().run(db_session, get_settings(), "b-1")
    assert len(outputs) == 1
    payload = outputs[0].structured_data
    assert payload["payee_name"] == "Netflix"
    assert payload["cadence"] == "monthly"
    assert payload["amount_cents"] == 1599
    assert payload["monthly_cost_cents"] == 1599
    assert payload["annual_cost_cents"] == 1599 * 12
    assert len(payload["occurrences"]) == 3
    assert outputs[0].dedup_key == "subscription:p-netflix:1599:monthly"


async def test_subscription_audit_ignores_irregular_intervals(
    db_session: AsyncSession, budget: Budget
) -> None:
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    db_session.add(Payee(id="p-shop", budget_id="b-1", name="Random Store"))
    today = _today()
    # Three same-amount charges but at irregular intervals (5, 20, 50 days ago).
    for i, days_ago in enumerate([5, 20, 50]):
        db_session.add(
            Transaction(
                id=f"t-irr-{i}",
                budget_id="b-1",
                account_id="a-1",
                payee_id="p-shop",
                category_id=None,
                date=today - timedelta(days=days_ago),
                amount_cents=-2500,
                memo=None,
                cleared="cleared",
                approved=True,
            )
        )
    await db_session.commit()

    outputs = await SubscriptionAuditGenerator().run(db_session, get_settings(), "b-1")
    assert outputs == []


async def test_subscription_audit_excludes_transfers(
    db_session: AsyncSession, budget: Budget
) -> None:
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    db_session.add(
        Account(
            id="a-2",
            budget_id="b-1",
            name="Savings",
            type="savings",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    # Transfer payee — same amount monthly, but should be excluded.
    db_session.add(
        Payee(
            id="p-transfer",
            budget_id="b-1",
            name="Transfer to Savings",
            transfer_account_id="a-2",
        )
    )
    today = _today()
    for i, days_ago in enumerate([1, 31, 61]):
        db_session.add(
            Transaction(
                id=f"t-xfer-{i}",
                budget_id="b-1",
                account_id="a-1",
                payee_id="p-transfer",
                category_id=None,
                date=today - timedelta(days=days_ago),
                amount_cents=-50000,
                memo=None,
                cleared="cleared",
                approved=True,
            )
        )
    await db_session.commit()

    outputs = await SubscriptionAuditGenerator().run(db_session, get_settings(), "b-1")
    assert outputs == []


async def test_spending_anomaly_flags_z_above_threshold(
    db_session: AsyncSession, budget: Budget
) -> None:
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    db_session.add(
        Category(
            id="c-grocery",
            budget_id="b-1",
            category_group_id=None,
            name="Groceries",
            hidden=False,
        )
    )
    today = _today()
    # 12 baseline weeks with some variance, current week at $400 — clear spike.
    baseline_cents = [
        -5000,
        -5500,
        -4500,
        -6000,
        -4000,
        -5000,
        -5500,
        -4500,
        -5000,
        -6000,
        -4000,
        -5500,
    ]
    txn_id = 0
    for week_back, amount in zip(range(12, 0, -1), baseline_cents, strict=True):
        center = today - timedelta(days=7 * week_back)
        db_session.add(
            Transaction(
                id=f"t-base-{txn_id}",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-grocery",
                payee_id=None,
                date=center,
                amount_cents=amount,
                memo=None,
                cleared="cleared",
                approved=True,
            )
        )
        txn_id += 1
    # Current week: 4 transactions of $100 = $400 spent in last 7 days.
    for i in range(4):
        db_session.add(
            Transaction(
                id=f"t-cur-{i}",
                budget_id="b-1",
                account_id="a-1",
                category_id="c-grocery",
                payee_id=None,
                date=today - timedelta(days=i),
                amount_cents=-10000,
                memo=None,
                cleared="cleared",
                approved=True,
            )
        )
    await db_session.commit()

    outputs = await SpendingAnomalyGenerator().run(db_session, get_settings(), "b-1")
    assert len(outputs) == 1
    payload = outputs[0].structured_data
    assert payload["category_id"] == "c-grocery"
    assert payload["current_week_spend_cents"] == 40000
    assert payload["z_score"] > 2.0
    assert len(payload["top_transactions"]) <= 3


async def test_spending_anomaly_ignores_small_absolute_deviation(
    db_session: AsyncSession, budget: Budget
) -> None:
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    db_session.add(
        Category(
            id="c-coffee",
            budget_id="b-1",
            category_group_id=None,
            name="Coffee",
            hidden=False,
        )
    )
    today = _today()
    # Baseline of $0 (no transactions), current week one $10 charge. The
    # absolute deviation is $10 < $25 floor so we should NOT flag.
    db_session.add(
        Transaction(
            id="t-coffee",
            budget_id="b-1",
            account_id="a-1",
            category_id="c-coffee",
            payee_id=None,
            date=today,
            amount_cents=-1000,
            memo=None,
            cleared="cleared",
            approved=True,
        )
    )
    await db_session.commit()

    outputs = await SpendingAnomalyGenerator().run(db_session, get_settings(), "b-1")
    assert outputs == []


async def test_cashflow_forecast_uses_history_to_project(
    db_session: AsyncSession, budget: Budget
) -> None:
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=100_000,
            on_budget=True,
            closed=False,
        )
    )
    today = _today()
    # 90 days of $1/day net positive: one $90 income transaction.
    db_session.add(
        Transaction(
            id="t-income",
            budget_id="b-1",
            account_id="a-1",
            category_id=None,
            payee_id=None,
            date=today - timedelta(days=30),
            amount_cents=9_000,
            memo=None,
            cleared="cleared",
            approved=True,
        )
    )
    await db_session.commit()

    outputs = await CashflowForecastGenerator().run(db_session, get_settings(), "b-1")
    assert len(outputs) == 1
    payload = outputs[0].structured_data
    assert payload["starting_balance_cents"] == 100_000
    assert payload["daily_net_cents"] == 100
    assert payload["projected_30d_cents"] == 100_000 + 100 * 30
    assert payload["projected_90d_cents"] == 100_000 + 100 * 90


async def test_cashflow_forecast_flat_projection_when_no_history(
    db_session: AsyncSession, budget: Budget
) -> None:
    """With on-budget accounts but no activity, the forecast is still produced
    so the user can see today's balance; the projection is just flat."""
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=42_000,
            on_budget=True,
            closed=False,
        )
    )
    await db_session.commit()
    outputs = await CashflowForecastGenerator().run(db_session, get_settings(), "b-1")
    assert len(outputs) == 1
    payload = outputs[0].structured_data
    assert payload["starting_balance_cents"] == 42_000
    assert payload["daily_net_cents"] == 0
    assert payload["projected_90d_cents"] == 42_000
    assert payload["top_spending_categories"] == []


async def test_cashflow_forecast_returns_empty_without_on_budget_accounts(
    db_session: AsyncSession, budget: Budget
) -> None:
    """If the only accounts are tracking (off-budget), there is no on-budget
    cashflow to project; the generator returns nothing."""
    db_session.add(
        Account(
            id="a-tracking",
            budget_id="b-1",
            name="Investment",
            type="otherAsset",
            balance_cents=1_000_000,
            on_budget=False,
            closed=False,
        )
    )
    await db_session.commit()
    outputs = await CashflowForecastGenerator().run(db_session, get_settings(), "b-1")
    assert outputs == []


async def test_cashflow_forecast_excludes_tracking_account_flows(
    db_session: AsyncSession, budget: Budget
) -> None:
    """A $-100k tracking-account transaction (e.g. an investment buy) must
    NOT drag the projection negative. Only on-budget activity counts."""
    db_session.add_all(
        [
            Account(
                id="a-1",
                budget_id="b-1",
                name="Checking",
                type="checking",
                balance_cents=50_000,
                on_budget=True,
                closed=False,
            ),
            Account(
                id="a-tracking",
                budget_id="b-1",
                name="Brokerage",
                type="otherAsset",
                balance_cents=0,
                on_budget=False,
                closed=False,
            ),
            Transaction(
                id="t-buy",
                budget_id="b-1",
                account_id="a-tracking",
                category_id=None,
                payee_id=None,
                date=_today() - timedelta(days=10),
                amount_cents=-10_000_000,  # $-100k investment buy
                memo="stock purchase",
                cleared="cleared",
                approved=True,
            ),
        ]
    )
    await db_session.commit()
    outputs = await CashflowForecastGenerator().run(db_session, get_settings(), "b-1")
    assert len(outputs) == 1
    payload = outputs[0].structured_data
    # Projection only reflects on-budget activity (none here), so it stays flat.
    assert payload["daily_net_cents"] == 0
    assert payload["projected_90d_cents"] == 50_000


async def test_goal_trajectory_emits_per_active_goal(
    db_session: AsyncSession, budget: Budget
) -> None:
    db_session.add_all(
        [
            Category(
                id="c-emergency",
                budget_id="b-1",
                category_group_id=None,
                name="Emergency Fund",
                hidden=False,
                goal_type="TB",
                goal_target_cents=1_000_000,  # $10k
                goal_target_month=None,
                goal_percentage_complete=40,
                goal_overall_left_cents=600_000,
                goal_months_to_budget=12,
            ),
            Category(
                id="c-vacation",
                budget_id="b-1",
                category_group_id=None,
                name="Vacation",
                hidden=False,
                goal_type="TBD",
                goal_target_cents=500_000,  # $5k
                goal_target_month=date.today() + timedelta(days=180),
                goal_percentage_complete=20,
                goal_overall_left_cents=400_000,
                goal_months_to_budget=6,
            ),
            Category(
                id="c-done",
                budget_id="b-1",
                category_group_id=None,
                name="Already Met",
                hidden=False,
                goal_type="TB",
                goal_target_cents=100_000,
                goal_percentage_complete=100,
                goal_overall_left_cents=0,
            ),
            Category(
                id="c-no-goal",
                budget_id="b-1",
                category_group_id=None,
                name="No goal",
                hidden=False,
            ),
        ]
    )
    await db_session.commit()

    outputs = await GoalTrajectoryGenerator().run(db_session, get_settings(), "b-1")
    category_ids = {o.structured_data["category_id"] for o in outputs}
    assert category_ids == {"c-emergency", "c-vacation"}

    by_id = {o.structured_data["category_id"]: o.structured_data for o in outputs}
    assert by_id["c-vacation"]["on_track"] is True
    assert by_id["c-vacation"]["target_date"] is not None
    assert by_id["c-emergency"]["target_date"] is None
    assert by_id["c-emergency"]["projected_completion_date"] is not None


async def test_execute_generator_dedups_on_second_run(
    db_session: AsyncSession, budget: Budget
) -> None:
    """Same dedup_key → upsert in place, second run reports as 'updated'."""

    class FixedGenerator(InsightGenerator):
        card_type = "test_fixed"
        cadence = "daily"

        async def run(self, session: AsyncSession, settings, budget_id: str):  # type: ignore[no-untyped-def]
            return [
                GeneratedInsight(
                    dedup_key="fixed:1",
                    title="hello",
                    summary="world",
                    structured_data={"card_type": "test_fixed", "value": 1},
                ),
            ]

    settings = get_settings()
    first = await execute_generator(FixedGenerator, db_session, settings, "b-1")
    assert first.insights_created == 1
    assert first.insights_updated == 0

    second = await execute_generator(FixedGenerator, db_session, settings, "b-1")
    assert second.insights_created == 0
    assert second.insights_updated == 1

    rows = (await db_session.execute(select(Insight))).scalars().all()
    assert len(rows) == 1
    assert rows[0].title == "hello"

    runs = (await db_session.execute(select(InsightRun))).scalars().all()
    assert len(runs) == 2
    assert {r.status for r in runs} == {"ok"}


async def test_execute_generator_records_failed_run(
    db_session: AsyncSession, budget: Budget
) -> None:
    class BrokenGenerator(InsightGenerator):
        card_type = "test_broken"
        cadence = "daily"

        async def run(self, session: AsyncSession, settings, budget_id: str):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

    outcome = await execute_generator(BrokenGenerator, db_session, get_settings(), "b-1")
    assert outcome.status == "error"
    assert outcome.error is not None and "boom" in outcome.error

    runs = (await db_session.execute(select(InsightRun))).scalars().all()
    assert len(runs) == 1
    assert runs[0].status == "error"
    assert runs[0].error is not None and "boom" in runs[0].error


async def _seed_category_drift_history(
    db_session: AsyncSession,
    *,
    category_id: str,
    category_name: str,
    monthly_outflows: list[int],
) -> None:
    """Build a 12-month synthetic spending history for one category, with
    one transaction per month dated on the 15th. `monthly_outflows` is
    oldest-first and positive (we negate so they land as outflow rows)."""
    today = date.today()
    db_session.add(
        Category(
            id=category_id,
            budget_id="b-1",
            category_group_id=None,
            name=category_name,
            hidden=False,
        )
    )
    for offset, amount in enumerate(monthly_outflows):
        # offset 0 = 11 months ago, offset 11 = current month.
        months_back = len(monthly_outflows) - 1 - offset
        year = today.year
        month = today.month - months_back
        while month <= 0:
            month += 12
            year -= 1
        db_session.add(
            Transaction(
                id=f"t-{category_id}-{offset}",
                budget_id="b-1",
                account_id="a-1",
                category_id=category_id,
                payee_id=None,
                date=date(year, month, 15),
                amount_cents=-amount,
                memo=None,
                cleared="cleared",
                approved=True,
            )
        )


async def test_category_drift_flags_upward_drift(db_session: AsyncSession, budget: Budget) -> None:
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    # First 9 months at $40, then trailing quarter (months 9-11 inclusive)
    # bumped to $400. The generator's trailing window is months 8-10 (the
    # three months before the current incomplete one at index 11), so the
    # baseline averages ~$40 and the trailing averages ~$400 — well above
    # the 15% / $50 thresholds.
    spend = [4000] * 9 + [40000, 40000, 40000]
    await _seed_category_drift_history(
        db_session,
        category_id="c-grocery",
        category_name="Groceries",
        monthly_outflows=spend,
    )
    await db_session.commit()

    outputs = await CategoryDriftGenerator().run(db_session, get_settings(), "b-1")
    assert len(outputs) == 1
    payload = outputs[0].structured_data
    assert payload["category_name"] == "Groceries"
    assert payload["direction"] == "up"
    assert payload["drift_pct"] > 0.5
    assert payload["drift_cents_per_month"] > 30000


async def test_category_drift_ignores_below_threshold(
    db_session: AsyncSession, budget: Budget
) -> None:
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    # Slight uptick: 10% in the trailing quarter — below the 15% gate.
    spend = [10000] * 9 + [11000, 11000, 11000]
    await _seed_category_drift_history(
        db_session,
        category_id="c-utility",
        category_name="Utilities",
        monthly_outflows=spend,
    )
    await db_session.commit()

    outputs = await CategoryDriftGenerator().run(db_session, get_settings(), "b-1")
    assert outputs == []


async def test_category_drift_flags_downward_drift(
    db_session: AsyncSession, budget: Budget
) -> None:
    db_session.add(
        Account(
            id="a-1",
            budget_id="b-1",
            name="Checking",
            type="checking",
            balance_cents=0,
            on_budget=True,
            closed=False,
        )
    )
    spend = [50000] * 9 + [5000, 5000, 5000]
    await _seed_category_drift_history(
        db_session,
        category_id="c-dining",
        category_name="Eating Out",
        monthly_outflows=spend,
    )
    await db_session.commit()

    outputs = await CategoryDriftGenerator().run(db_session, get_settings(), "b-1")
    assert len(outputs) == 1
    assert outputs[0].structured_data["direction"] == "down"
    assert outputs[0].structured_data["drift_cents_per_month"] < -30000
