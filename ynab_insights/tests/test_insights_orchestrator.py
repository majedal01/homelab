"""Parallel orchestrator (v2.6f).

The orchestrator runs generators concurrently with per-generator
timeouts. These tests cover the three invariants:

1. A failing generator doesn't suppress the others.
2. A timed-out generator doesn't suppress the others.
3. Generators actually run in parallel (wall time ~ slowest, not the sum).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Sequence
from datetime import datetime
from typing import ClassVar

import pytest
from pydantic import SecretStr

from app.insights.base import (
    GeneratedInsight,
    Insight,
    InsightGenerator,
    run_all_generators,
)
from app.snapshot.models import YnabSnapshot


def _snapshot() -> YnabSnapshot:
    return YnabSnapshot(
        budget_id="b1",
        budget_name="b1",
        currency_iso="USD",
        fetched_at=datetime(2026, 5, 25),
        accounts=[],
        categories=[],
        payees=[],
        transactions=[],
    )


class _OkFast(InsightGenerator):
    card_type: ClassVar[str] = "_test_ok_fast"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        await asyncio.sleep(0.1)
        return [
            GeneratedInsight(
                dedup_key="fast:1",
                title="fast",
                summary="ok",
                structured_data={"card_type": "_test_ok_fast"},
            )
        ]


class _OkSlow(InsightGenerator):
    card_type: ClassVar[str] = "_test_ok_slow"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        await asyncio.sleep(0.3)
        return [
            GeneratedInsight(
                dedup_key="slow:1",
                title="slow",
                summary="ok",
                structured_data={"card_type": "_test_ok_slow"},
            )
        ]


class _Raises(InsightGenerator):
    card_type: ClassVar[str] = "_test_raises"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        raise RuntimeError("boom")


class _Hangs(InsightGenerator):
    card_type: ClassVar[str] = "_test_hangs"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        await asyncio.sleep(10)
        return []


@pytest.mark.asyncio
async def test_one_failure_does_not_suppress_others() -> None:
    merged, records, _ = await run_all_generators(
        generators=[_OkFast, _Raises, _OkSlow],
        snapshot=_snapshot(),
        anthropic_key=None,
        anthropic_model=None,
        existing={},
        next_id=1,
        next_run_id=1,
    )
    statuses = {r.card_type: r.status for r in records}
    assert statuses == {
        "_test_ok_fast": "ok",
        "_test_raises": "error",
        "_test_ok_slow": "ok",
    }
    titles = {i.title for i in merged}
    assert titles == {"fast", "slow"}
    raises_record = next(r for r in records if r.card_type == "_test_raises")
    assert raises_record.error is not None
    assert "RuntimeError" in raises_record.error


@pytest.mark.asyncio
async def test_timeout_isolated_to_one_generator() -> None:
    merged, records, _ = await run_all_generators(
        generators=[_OkFast, _Hangs],
        snapshot=_snapshot(),
        anthropic_key=None,
        anthropic_model=None,
        existing={},
        next_id=1,
        next_run_id=1,
        per_generator_timeout_s=0.2,
    )
    by_type = {r.card_type: r for r in records}
    assert by_type["_test_ok_fast"].status == "ok"
    assert by_type["_test_hangs"].status == "error"
    assert by_type["_test_hangs"].error is not None
    assert "timeout" in by_type["_test_hangs"].error
    assert any(i.title == "fast" for i in merged)


@pytest.mark.asyncio
async def test_generators_run_in_parallel() -> None:
    """Two ~300ms generators should finish in well under their sum."""
    started = time.perf_counter()
    _, records, _ = await run_all_generators(
        generators=[_OkSlow, _OkSlow],
        snapshot=_snapshot(),
        anthropic_key=None,
        anthropic_model=None,
        existing={},
        next_id=1,
        next_run_id=1,
    )
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5, (
        f"orchestrator took {elapsed:.2f}s; expected ~0.3s if generators run concurrently"
    )
    assert all(r.status == "ok" for r in records)


class _OverridesCardType(InsightGenerator):
    """Registers as one card_type but emits a card of another, exercising
    the GeneratedInsight.card_type override (e.g. the goals generator
    emitting goal_setup_prompt / emergency_fund_coverage)."""

    card_type: ClassVar[str] = "_test_parent"
    cadence: ClassVar[str] = "daily"

    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
        anthropic_model: str | None = None,
    ) -> Sequence[GeneratedInsight]:
        return [
            GeneratedInsight(
                dedup_key="override:1",
                title="overridden",
                summary="ok",
                structured_data={"card_type": "_test_child"},
                card_type="_test_child",
            )
        ]


@pytest.mark.asyncio
async def test_card_type_override_is_stamped_on_insight() -> None:
    """The emitted card's own card_type wins over the generator's; the run
    record still reflects the generator. This is what lets the goals
    generator ship a goal_setup_prompt card instead of a goal_trajectory."""
    merged, records, _ = await run_all_generators(
        generators=[_OverridesCardType],
        snapshot=_snapshot(),
        anthropic_key=None,
        anthropic_model=None,
        existing={},
        next_id=1,
        next_run_id=1,
    )
    assert len(merged) == 1
    assert merged[0].card_type == "_test_child"
    assert records[0].card_type == "_test_parent"


@pytest.mark.asyncio
async def test_existing_insight_is_upserted_not_duplicated() -> None:
    snapshot = _snapshot()
    prior = Insight(
        id=42,
        budget_id=snapshot.budget_id,
        card_type="_test_ok_fast",
        dedup_key="fast:1",
        title="old",
        summary="old",
        structured_data={},
        generated_at=datetime(2026, 1, 1),
        refreshed_at=datetime(2026, 1, 1),
        llm_enhanced=False,
    )
    existing = {(snapshot.budget_id, "fast:1"): prior}
    merged, records, _ = await run_all_generators(
        generators=[_OkFast],
        snapshot=snapshot,
        anthropic_key=None,
        anthropic_model=None,
        existing=existing,
        next_id=100,
        next_run_id=1,
    )
    assert len(merged) == 1
    assert merged[0].id == 42
    assert merged[0].title == "fast"
    assert records[0].insights_created == 0
    assert records[0].insights_updated == 1
