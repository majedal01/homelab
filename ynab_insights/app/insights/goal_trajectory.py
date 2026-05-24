"""Goal Trajectory generator.

For each Category with a non-zero goal target that is not yet 100% complete,
project completion using YNAB's goal fields surfaced in the snapshot.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import ClassVar

from pydantic import SecretStr

from app.insights.base import GeneratedInsight, InsightGenerator, register_generator
from app.insights.llm import enhance_copy
from app.insights.schemas import GoalTrajectoryData
from app.snapshot.models import YnabSnapshot


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
    ) -> Sequence[GeneratedInsight]:
        today = date.today()
        categories = [
            c for c in snapshot.categories if c.goal_target_cents is not None and not c.hidden
        ]

        outputs: list[GeneratedInsight] = []
        for cat in categories:
            target = cat.goal_target_cents or 0
            if target <= 0:
                continue
            percent = cat.goal_percentage_complete or 0
            if percent >= 100:
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

        return outputs
