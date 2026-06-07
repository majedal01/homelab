"""Generator framework: abstract base, registry, and orchestrator (v2.5).

Generators take a `YnabSnapshot` and an Anthropic key. They are side-effect
free; the orchestrator runs them and produces in-memory `Insight` and
`RunRecord` objects to attach to the session.

Importing a generator module is enough to register it (the
`@register_generator` decorator runs at class-definition time).
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import SecretStr

from app.observability import metrics
from app.snapshot.models import YnabSnapshot

logger = logging.getLogger(__name__)

# How long any single generator may run before the orchestrator gives up
# and records a timeout. Sized to cover an LLM-enhanced generator hitting
# enhance_copy's 5s timeout per insight on a budget with a handful of
# results, plus headroom for network jitter.
DEFAULT_PER_GENERATOR_TIMEOUT_S: float = 30.0


@dataclass
class GeneratedInsight:
    """Output unit of a generator. Orchestrator wraps it as an `Insight`."""

    dedup_key: str
    title: str
    summary: str
    structured_data: dict[str, Any]
    llm_enhanced: bool = False
    # Optional override: a generator may emit cards of a different card_type
    # than its registration key (e.g. the goals generator emits
    # emergency_fund_coverage / savings_rate_trend / goal_setup_prompt). When
    # None, the orchestrator stamps the generator's own card_type.
    card_type: str | None = None


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
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        """Detect insights from the in-memory snapshot. Side-effect-free.

        `anthropic_model` is the user's per-session choice; None means
        fall through to whatever `enhance_copy`'s default is.
        """


_REGISTRY: dict[str, type[InsightGenerator]] = {}


def register_generator(cls: type[InsightGenerator]) -> type[InsightGenerator]:
    if not getattr(cls, "card_type", None):
        raise TypeError(f"{cls.__name__} must set `card_type` to register")
    if cls.card_type in _REGISTRY and _REGISTRY[cls.card_type] is not cls:
        raise RuntimeError(f"duplicate generator registration for card_type={cls.card_type!r}")
    _REGISTRY[cls.card_type] = cls
    return cls


def all_generators() -> list[type[InsightGenerator]]:
    """Snapshot of every registered generator, sorted by card_type."""
    return [_REGISTRY[k] for k in sorted(_REGISTRY)]


def get_generator(card_type: str) -> type[InsightGenerator] | None:
    return _REGISTRY.get(card_type)


@dataclass
class _Invocation:
    """The async-completed side of one generator run.

    Held briefly between `asyncio.gather` returning and the sequential
    merge step that allocates ids and produces final `Insight` objects.
    """

    generator_cls: type[InsightGenerator]
    outputs: Sequence[GeneratedInsight]
    status: str
    error: str | None
    started_at: datetime
    finished_at: datetime
    duration_ms: int


async def _invoke_generator(
    generator_cls: type[InsightGenerator],
    snapshot: YnabSnapshot,
    anthropic_key: SecretStr | None,
    anthropic_model: str | None,
    timeout_s: float,
) -> _Invocation:
    """Run one generator with a wall-clock timeout. Never raises."""
    started = datetime.now(UTC)
    perf_started = time.perf_counter()
    outputs: Sequence[GeneratedInsight] = ()
    error: str | None = None
    status = "ok"

    try:
        outputs = await asyncio.wait_for(
            generator_cls().run(snapshot, anthropic_key, anthropic_model),
            timeout=timeout_s,
        )
    except TimeoutError:
        # `asyncio.wait_for` raises the builtin TimeoutError on Python 3.11+.
        status = "error"
        error = f"timeout after {timeout_s:.1f}s"
        logger.warning(
            "generator %s timed out (budget=%s, timeout=%.1fs)",
            generator_cls.card_type,
            snapshot.budget_id,
            timeout_s,
        )
    except Exception as exc:  # noqa: BLE001
        # One bad generator must not crash the request. The orchestrator
        # records the error in its RunRecord; everything else proceeds.
        status = "error"
        error = f"{type(exc).__name__}: {exc}"
        logger.exception(
            "generator %s failed for budget %s",
            generator_cls.card_type,
            snapshot.budget_id,
        )

    finished = datetime.now(UTC)
    duration_ms = int((time.perf_counter() - perf_started) * 1000)
    return _Invocation(
        generator_cls=generator_cls,
        outputs=outputs,
        status=status,
        error=error,
        started_at=started,
        finished_at=finished,
        duration_ms=duration_ms,
    )


async def run_all_generators(
    *,
    generators: Sequence[type[InsightGenerator]],
    snapshot: YnabSnapshot,
    anthropic_key: SecretStr | None,
    anthropic_model: str | None,
    existing: dict[tuple[str, str], Insight],
    next_id: int,
    next_run_id: int,
    per_generator_timeout_s: float = DEFAULT_PER_GENERATOR_TIMEOUT_S,
) -> tuple[list[Insight], list[RunRecord], list[int]]:
    """Run every generator concurrently. Merge results sequentially.

    Concurrency: each generator runs under its own `asyncio.wait_for`, so
    one slow generator cannot stall the others. A timeout records a failed
    `RunRecord` with `error="timeout after Xs"` and produces no insights.

    Sequential merge: id allocation is the one piece that can't be done in
    parallel without coordinating a shared counter, so it happens here, in
    the order `generators` was passed. Existing insights are upserted
    in-place: refresh content + refreshed_at, preserve `dismissed_at` and
    `id`. The caller writes the returned insight list back to the session.

    Returns (insights, records, run_ids) where `insights` is the full
    merged set (existing entries possibly mutated + new entries appended)
    and `records` / `run_ids` are aligned with `generators` order.
    """
    invocations = await asyncio.gather(
        *(
            _invoke_generator(
                cls, snapshot, anthropic_key, anthropic_model, per_generator_timeout_s
            )
            for cls in generators
        )
    )

    by_key: dict[tuple[str, str], Insight] = dict(existing)
    records: list[RunRecord] = []
    run_ids: list[int] = []

    for inv in invocations:
        created = 0
        updated = 0
        for output in inv.outputs:
            key = (snapshot.budget_id, output.dedup_key)
            now = datetime.now(UTC)
            card_type = output.card_type or inv.generator_cls.card_type
            prior = by_key.get(key)
            if prior is None:
                insight = Insight(
                    id=next_id,
                    budget_id=snapshot.budget_id,
                    card_type=card_type,
                    dedup_key=output.dedup_key,
                    title=output.title,
                    summary=output.summary,
                    structured_data=output.structured_data,
                    generated_at=now,
                    refreshed_at=now,
                    llm_enhanced=output.llm_enhanced,
                )
                next_id += 1
                by_key[key] = insight
                created += 1
                metrics.insights_generated_total.labels(card_type=card_type).inc()
            else:
                prior.title = output.title
                prior.summary = output.summary
                prior.structured_data = output.structured_data
                prior.refreshed_at = now
                prior.llm_enhanced = output.llm_enhanced
                updated += 1

        record = RunRecord(
            id=next_run_id,
            card_type=inv.generator_cls.card_type,
            started_at=inv.started_at,
            finished_at=inv.finished_at,
            status=inv.status,
            duration_ms=inv.duration_ms,
            insights_created=created,
            insights_updated=updated,
            error=inv.error,
        )
        records.append(record)
        run_ids.append(next_run_id)
        next_run_id += 1

    return list(by_key.values()), records, run_ids
