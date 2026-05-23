"""Generator framework: abstract base, registry, and orchestrator.

A generator is a class subclassing `InsightGenerator` with a `card_type`,
a `cadence`, and an async `run()` that returns `GeneratedInsight`
objects. Importing a generator module is enough to register it (the
`@register_generator` decorator runs at class-definition time).

The orchestrator (`execute_generator`) is the only path that writes to
`insights` and `insight_runs`. It captures timing, upserts by
`(budget_id, dedup_key)`, and records the run regardless of outcome.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Insight, InsightRun
from app.services.metrics import counters

logger = logging.getLogger(__name__)


@dataclass
class GeneratedInsight:
    """Output unit of a generator. The orchestrator turns it into an Insight row."""

    dedup_key: str
    title: str
    summary: str
    structured_data: dict[str, Any]
    llm_enhanced: bool = False
    # Hint to the orchestrator for which budget owns this insight when a
    # generator covers multiple budgets in one run. Defaults to the budget
    # passed into `run()`.
    budget_id: str | None = None


@dataclass
class RunOutcome:
    """Summary returned by `execute_generator`. Mirrors the InsightRun row."""

    run_id: int
    status: str
    insights_created: int
    insights_updated: int
    duration_ms: int
    error: str | None = None
    insight_ids: list[int] = field(default_factory=list)


class InsightGenerator(ABC):
    """Base class for insight generators."""

    card_type: ClassVar[str]
    # Hint for the scheduler; the actual cron / interval wiring lives in
    # `app.services.scheduler`. Values: "daily" or "weekly".
    cadence: ClassVar[str]

    @abstractmethod
    async def run(
        self,
        session: AsyncSession,
        settings: Settings,
        budget_id: str,
    ) -> Sequence[GeneratedInsight]:
        """Detect insights for the given budget. Side-effect-free; the
        orchestrator persists the returned `GeneratedInsight`s."""


_REGISTRY: dict[str, type[InsightGenerator]] = {}


def register_generator(cls: type[InsightGenerator]) -> type[InsightGenerator]:
    """Decorator that registers a generator class by its `card_type`."""

    if not getattr(cls, "card_type", None):
        raise TypeError(f"{cls.__name__} must set `card_type` to register")
    if cls.card_type in _REGISTRY and _REGISTRY[cls.card_type] is not cls:
        raise RuntimeError(
            f"duplicate generator registration for card_type={cls.card_type!r}: "
            f"{_REGISTRY[cls.card_type]!r} vs {cls!r}"
        )
    _REGISTRY[cls.card_type] = cls
    return cls


def all_generators() -> list[type[InsightGenerator]]:
    """Snapshot of every registered generator class, sorted by card_type for
    deterministic iteration order in the orchestrator and on the runs page."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def get_generator(card_type: str) -> type[InsightGenerator] | None:
    return _REGISTRY.get(card_type)


async def execute_generator(
    generator_cls: type[InsightGenerator],
    session: AsyncSession,
    settings: Settings,
    budget_id: str,
) -> RunOutcome:
    """Run a generator and persist its output.

    Opens an `InsightRun` row before calling `run()`, upserts each returned
    `GeneratedInsight` by `(budget_id, dedup_key)`, and closes the run with
    final status and counts. Exceptions are caught so a misbehaving generator
    can't crash the scheduler or the on-demand endpoint.
    """
    started = datetime.now(UTC)
    run = InsightRun(
        card_type=generator_cls.card_type,
        started_at=started,
        status="running",
    )
    session.add(run)
    await session.flush()  # populate run.id

    created = 0
    updated = 0
    insight_ids: list[int] = []
    error: str | None = None

    perf_started = time.perf_counter()
    try:
        outputs = await generator_cls().run(session, settings, budget_id)
        for output in outputs:
            owner_budget_id = output.budget_id or budget_id
            stmt = select(Insight).where(
                Insight.budget_id == owner_budget_id,
                Insight.dedup_key == output.dedup_key,
            )
            existing = (await session.execute(stmt)).scalar_one_or_none()
            now = datetime.now(UTC)
            if existing is None:
                insight = Insight(
                    budget_id=owner_budget_id,
                    card_type=generator_cls.card_type,
                    dedup_key=output.dedup_key,
                    title=output.title,
                    summary=output.summary,
                    structured_data=output.structured_data,
                    generated_at=now,
                    refreshed_at=now,
                    llm_enhanced=output.llm_enhanced,
                )
                session.add(insight)
                await session.flush()
                insight_ids.append(insight.id)
                created += 1
            else:
                existing.title = output.title
                existing.summary = output.summary
                existing.structured_data = output.structured_data
                existing.refreshed_at = now
                existing.llm_enhanced = output.llm_enhanced
                insight_ids.append(existing.id)
                updated += 1

        run.status = "ok"
        counters.insight_runs_ok += 1
    except Exception as exc:  # noqa: BLE001
        # Caught broadly: scheduler must not crash on a misbehaving generator.
        logger.exception("generator %s failed for budget %s", generator_cls.card_type, budget_id)
        error = f"{type(exc).__name__}: {exc}"
        run.status = "error"
        run.error = error
        counters.insight_runs_failed += 1
    finally:
        run.finished_at = datetime.now(UTC)
        duration_ms = int((time.perf_counter() - perf_started) * 1000)
        run.duration_ms = duration_ms
        run.insights_created = created
        run.insights_updated = updated
        await session.commit()

    return RunOutcome(
        run_id=run.id,
        status=run.status,
        insights_created=created,
        insights_updated=updated,
        duration_ms=duration_ms,
        error=error,
        insight_ids=insight_ids,
    )
