"""Goal Trajectory generator.

For each Category with a non-zero goal target that is not yet 100% complete,
project completion using YNAB's goal fields surfaced in the snapshot.

When the loop ends up emitting zero trajectory cards — either because
the user hasn't configured any goals OR because every goal got filtered
out (all 100% complete, zero target, hidden, etc.) — the generator
falls back to ONE empty-state card with card_type=goal_setup_prompt.
That card lists the user's top spending categories as candidate goal
targets, so the Goals section never reads as "broken empty"; it always
shows either real trajectories or a path to set one up.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import ClassVar

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.diagnostics import diag
from app.insights.llm import enhance_copy
from app.insights.schemas import (
    GoalSetupPromptCategory,
    GoalSetupPromptData,
    GoalTrajectoryData,
)
from app.snapshot.models import YnabSnapshot
from app.snapshot.queries import spending_by_category


def _add_months(start: date, months: int) -> date:
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    return date(year, month, 1)


@register_generator
class GoalTrajectoryGenerator(InsightGenerator):
    card_type: ClassVar[str] = "goal_trajectory"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        categories = [
            c for c in snapshot.categories if c.goal_target_cents is not None and not c.hidden
        ]
        diag(
            "goal_trajectory",
            "start",
            total_categories=len(snapshot.categories),
            categories_with_goals=len(categories),
        )

        if not categories:
            prompt = _build_empty_state_prompt(snapshot, today)
            diag("goal_trajectory", "empty_state", reason="no_goals_configured")
            return [prompt] if prompt is not None else []

        outputs: list[GeneratedInsight] = []
        skips: dict[str, int] = {}
        for cat in categories:
            target = cat.goal_target_cents or 0
            if target <= 0:
                skips["zero_target"] = skips.get("zero_target", 0) + 1
                continue
            percent = cat.goal_percentage_complete or 0
            if percent >= 100:
                skips["already_complete"] = skips.get("already_complete", 0) + 1
                continue

            remaining = cat.goal_overall_left_cents
            if remaining is None:
                remaining = max(0, target - int(target * percent / 100))
            progress = target - remaining
            months_to_target = cat.goal_months_to_budget
            current_monthly = 0
            if months_to_target and months_to_target > 0:
                current_monthly = round(remaining / months_to_target)
            projected_completion: date | None = None
            on_track: bool | None = None
            if months_to_target and months_to_target > 0:
                projected_completion = _add_months(today, months_to_target)
                if cat.goal_target_month is not None:
                    on_track = projected_completion <= cat.goal_target_month

            data = GoalTrajectoryData(
                category_id=cat.id,
                category_name=cat.name,
                goal_type=cat.goal_type or "unknown",
                target_cents=target,
                progress_cents=progress,
                remaining_cents=remaining,
                percent_complete=min(percent, 99),
                current_monthly_contribution_cents=current_monthly,
                target_date=cat.goal_target_month,
                projected_completion_date=projected_completion,
                months_to_target=months_to_target,
                on_track=on_track,
            )

            target_dollars = target / 100
            remaining_dollars = remaining / 100
            if cat.goal_target_month is not None and on_track is False:
                pace_phrase = f"behind your {cat.goal_target_month.strftime('%b %Y')} target"
            elif cat.goal_target_month is not None and on_track is True:
                pace_phrase = f"on pace for your {cat.goal_target_month.strftime('%b %Y')} target"
            elif projected_completion is not None:
                pace_phrase = f"on pace to finish around {projected_completion.strftime('%b %Y')}"
            else:
                pace_phrase = "no current pace recorded"

            fallback_title = (
                f"{cat.name}: ${remaining_dollars:,.0f} to go of ${target_dollars:,.0f}"
            )
            fallback_summary = (
                f"You're {percent}% of the way to {cat.name} "
                f"(${target_dollars:,.0f}), {pace_phrase}."
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
                    dedup_key=f"goal:{cat.id}:{today.strftime('%Y-%m')}",
                    title=enhanced.title,
                    summary=enhanced.summary,
                    structured_data=data.model_dump(mode="json"),
                    llm_enhanced=enhanced.used_llm,
                )
            )

        for reason, count in skips.items():
            diag("goal_trajectory", "skipped", reason=reason, count=count)

        if not outputs:
            # Categories had goal targets but every single one filtered out
            # (all complete, zero target, hidden). Fall back to the empty-
            # state prompt so the Goals section is never silently empty.
            prompt = _build_empty_state_prompt(snapshot, today)
            diag(
                "goal_trajectory",
                "empty_state",
                reason="all_goals_filtered",
            )
            return [prompt] if prompt is not None else []

        diag("goal_trajectory", "finished", insights_emitted=len(outputs))
        return outputs


def _build_empty_state_prompt(snapshot: YnabSnapshot, today: date) -> GeneratedInsight | None:
    """Build the goal_setup_prompt card listing top spending categories.

    Ranks by trailing 90d spend so the categories feel current. Returns
    None on a snapshot with literally no expense activity (the empty
    prompt would be a useless card with no candidates to suggest)."""
    ninety_days_ago = today - timedelta(days=90)
    top = spending_by_category(snapshot, ninety_days_ago, today)
    # Only include real categories; the "Uncategorized" pseudo-id with
    # category_id=None wouldn't be settable as a YNAB goal.
    candidates = [row for row in top if row.category_id is not None][:5]
    if not candidates:
        return None

    payload = GoalSetupPromptData(
        top_categories=[
            GoalSetupPromptCategory(
                category_id=row.category_id,  # type: ignore[arg-type]
                category_name=row.category_name or "Uncategorized",
                # spent_cents is negative net spend; flip to positive.
                monthly_avg_spend_cents=round(-row.spent_cents / 3),
            )
            for row in candidates
        ]
    )

    return GeneratedInsight(
        dedup_key=f"goal_setup_prompt:{snapshot.budget_id}:{today.strftime('%Y-%m')}",
        title="Set a goal to start tracking",
        summary=(
            "No goals are set in YNAB yet. Pick one of your top spending "
            "categories and set a target to see projected trajectories here."
        ),
        structured_data=payload.model_dump(mode="json"),
        llm_enhanced=False,
    )
