"""Generator framework: abstract base, registry, and orchestrator (v2.5).

Generators take a `YnabSnapshot` and an Anthropic key. They are side-effect
free; the orchestrator runs them and produces in-memory `Insight` and
`RunRecord` objects to attach to the session.

Importing a generator module is enough to register it (the
`@register_generator` decorator runs at class-definition time).
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import SecretStr

from app.snapshot.models import YnabSnapshot

logger = logging.getLogger(__name__)


@dataclass
class GeneratedInsight:
    """Output unit of a generator. Orchestrator wraps it as an `Insight`."""

    dedup_key: str
    title: str
    summary: str
    structured_data: dict[str, Any]
    llm_enhanced: bool = False


@dataclass
class Insight:
    """In-memory insight, session-scoped. Same shape as the old DB row."""

    id: int
    budget_id: str
    card_type: str
    dedup_key: str
    title: str
    summary: str
    structured_data: dict[str, Any]
    generated_at: datetime
    refreshed_at: datetime
    llm_enhanced: bool
    dismissed_at: datetime | None = None


@dataclass
class RunRecord:
    """Observability record for one generator run."""

    id: int
    card_type: str
    started_at: datetime
    finished_at: datetime | None
    status: str  # 'ok' | 'error'
    duration_ms: int
    insights_created: int
    insights_updated: int
    error: str | None = None


@dataclass
class RunOutcome:
    """Summary returned by `execute_generator`."""

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
    # Scheduling hint: not used in v2.5 (generation is on-demand) but kept for
    # the metadata UI ("this card refreshes weekly").
    cadence: ClassVar[str]

    @abstractmethod
    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
    ) -> Sequence[GeneratedInsight]:
        """Detect insights from the in-memory snapshot. Side-effect-free."""


_REGISTRY: dict[str, type[InsightGenerator]] = {}


def register_generator(cls: type[InsightGenerator]) -> type[InsightGenerator]:
    if not getattr(cls, "card_type", None):
        raise TypeError(f"{cls.__name__} must set `card_type` to register")
    if cls.card_type in _REGISTRY and _REGISTRY[cls.card_type] is not cls:
        raise RuntimeError(
            f"duplicate generator registration for card_type={cls.card_type!r}"
        )
    _REGISTRY[cls.card_type] = cls
    return cls


def all_generators() -> list[type[InsightGenerator]]:
    """Snapshot of every registered generator, sorted by card_type."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def get_generator(card_type: str) -> type[InsightGenerator] | None:
    return _REGISTRY.get(card_type)


async def execute_generator(
    generator_cls: type[InsightGenerator],
    snapshot: YnabSnapshot,
    anthropic_key: SecretStr | None,
    *,
    next_id: int,
    next_run_id: int,
    existing: dict[tuple[str, str], Insight] | None = None,
) -> tuple[RunOutcome, list[Insight], RunRecord]:
    """Run one generator. Returns (outcome, updated insight list, run record).

    `existing` maps (budget_id, dedup_key) -> Insight so we can upsert
    in-place: refresh content + refreshed_at, preserve dismissed_at and id.
    The caller (router) merges the returned `insights` list back into the
    session.
    """
    started = datetime.now(UTC)
    perf_started = time.perf_counter()

    created = 0
    updated = 0
    insight_ids: list[int] = []
    new_or_updated: list[Insight] = []
    error: str | None = None

    by_key = existing or {}

    try:
        outputs = await generator_cls().run(snapshot, anthropic_key)
        for output in outputs:
            key = (snapshot.budget_id, output.dedup_key)
            now = datetime.now(UTC)
            prior = by_key.get(key)
            if prior is None:
                insight = Insight(
                    id=next_id,
                    budget_id=snapshot.budget_id,
                    card_type=generator_cls.card_type,
                    dedup_key=output.dedup_key,
                    title=output.title,
                    summary=output.summary,
                    structured_data=output.structured_data,
                    generated_at=now,
                    refreshed_at=now,
                    llm_enhanced=output.llm_enhanced,
                )
                next_id += 1
                new_or_updated.append(insight)
                insight_ids.append(insight.id)
                created += 1
            else:
                prior.title = output.title
                prior.summary = output.summary
                prior.structured_data = output.structured_data
                prior.refreshed_at = now
                prior.llm_enhanced = output.llm_enhanced
                new_or_updated.append(prior)
                insight_ids.append(prior.id)
                updated += 1
        status = "ok"
    except Exception as exc:  # noqa: BLE001
        # Caught broadly: one bad generator must not crash the request.
        logger.exception(
            "generator %s failed for budget %s",
            generator_cls.card_type,
            snapshot.budget_id,
        )
        error = f"{type(exc).__name__}: {exc}"
        status = "error"

    finished = datetime.now(UTC)
    duration_ms = int((time.perf_counter() - perf_started) * 1000)

    record = RunRecord(
        id=next_run_id,
        card_type=generator_cls.card_type,
        started_at=started,
        finished_at=finished,
        status=status,
        duration_ms=duration_ms,
        insights_created=created,
        insights_updated=updated,
        error=error,
    )
    outcome = RunOutcome(
        run_id=next_run_id,
        status=status,
        insights_created=created,
        insights_updated=updated,
        duration_ms=duration_ms,
        error=error,
        insight_ids=insight_ids,
    )
    return outcome, new_or_updated, record
