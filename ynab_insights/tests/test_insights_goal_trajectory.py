"""Goal Trajectory (v2.6g): empty-state branch.

Existing v2.4 behavior (real trajectory cards when goals exist) wasn't
covered by tests. v2.6g adds:

- When the user has no goals: emit ONE goal_setup_prompt card listing
  top spending categories.
- When goals exist: emit per-category trajectory cards as before.
- When goals exist AND none qualify (all 100% complete): zero output is
  OK; the section will be empty rather than mis-prompted.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from app.insights.goal_trajectory import GoalTrajectoryGenerator
from app.snapshot.models import Account, Category, Transaction, YnabSnapshot

CHECKING = Account(
    id="acct-1",
    name="Checking",
    type="checking",
    on_budget=True,
    closed=False,
    balance_cents=500000,
)


def _snapshot(cats: list[Category], txns: list[Transaction]) -> YnabSnapshot:
    return YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=[CHECKING],
        categories=cats,
        payees=[],
        transactions=txns,
    )


def _txn(d: date, cat_id: str, amount: int, **kw: Any) -> Transaction:
    return Transaction(
        id=f"t-{cat_id}-{d.isoformat()}-{amount}",
        date=d,
        amount_cents=amount,
        account_id="acct-1",
        category_id=cat_id,
        **kw,
    )


async def test_no_goals_emits_setup_prompt() -> None:
    """User has spending categories but none have goal_target_cents."""
    today = date.today()
    cats = [
        Category(id="cat-groc", name="Groceries"),
        Category(id="cat-rent", name="Rent"),
        Category(id="cat-fun", name="Fun"),
    ]
    txns: list[Transaction] = []
    # Some spending so candidates are non-empty
    for d_offset in (60, 30, 10):
        txns.append(_txn(today - timedelta(days=d_offset), "cat-rent", -150000))
        txns.append(_txn(today - timedelta(days=d_offset), "cat-groc", -40000))
        txns.append(_txn(today - timedelta(days=d_offset), "cat-fun", -10000))
    snapshot = _snapshot(cats, txns)
    insights = await GoalTrajectoryGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    payload = insights[0].structured_data
    assert payload["card_type"] == "goal_setup_prompt"
    # Top categories ranked by spend
    cat_ids = [c["category_id"] for c in payload["top_categories"]]
    assert cat_ids[0] == "cat-rent", f"Expected Rent first, got {cat_ids}"


async def test_no_goals_no_spending_no_card() -> None:
    """User has no goals AND no spending -> no candidates -> no card.
    Better empty-empty than a card that says 'set a goal on nothing'."""
    cats = [Category(id="cat-x", name="X")]
    snapshot = _snapshot(cats, [])
    insights = await GoalTrajectoryGenerator().run(snapshot, anthropic_key=None)
    assert insights == []


async def test_user_with_goals_emits_trajectory_cards() -> None:
    """When goals exist, the empty-state prompt should NOT fire — just
    real trajectory cards."""
    today = date.today()
    cats = [
        Category(
            id="cat-vac",
            name="Vacation",
            goal_target_cents=200000,
            goal_percentage_complete=40,
            goal_overall_left_cents=120000,
            goal_months_to_budget=8,
            goal_type="TBD",
        ),
    ]
    snapshot = _snapshot(cats, [_txn(today, "cat-vac", -1000)])
    insights = await GoalTrajectoryGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["card_type"] == "goal_trajectory"


async def test_all_goals_complete_falls_back_to_empty_state() -> None:
    """User has goals in YNAB but every one is 100% complete. v2.6g
    initially returned zero cards here — now falls back to the empty-
    state prompt so the Goals section is never silently empty."""
    today = date.today()
    cats = [
        Category(
            id="cat-done",
            name="Vacation",
            goal_target_cents=200000,
            goal_percentage_complete=100,
            goal_overall_left_cents=0,
            goal_months_to_budget=0,
            goal_type="TBD",
        ),
        Category(id="cat-groc", name="Groceries"),
    ]
    txns = [_txn(today - timedelta(days=10), "cat-groc", -40000)]
    snapshot = _snapshot(cats, txns)
    insights = await GoalTrajectoryGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["card_type"] == "goal_setup_prompt"


async def test_zero_target_goals_fall_back_to_empty_state() -> None:
    """Same idea: every goal-tagged category has target 0, so loop
    skips them all -> empty-state prompt."""
    today = date.today()
    cats = [
        Category(
            id="cat-empty",
            name="Empty goal",
            goal_target_cents=0,
            goal_percentage_complete=0,
            goal_type="TBD",
        ),
        Category(id="cat-groc", name="Groceries"),
    ]
    txns = [_txn(today - timedelta(days=5), "cat-groc", -40000)]
    snapshot = _snapshot(cats, txns)
    insights = await GoalTrajectoryGenerator().run(snapshot, anthropic_key=None)
    assert len(insights) == 1
    assert insights[0].structured_data["card_type"] == "goal_setup_prompt"
