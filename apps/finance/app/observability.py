"""Prometheus counters + gauges.

Single module so call sites just `from app.observability import metrics`
and increment by name. The metric definitions live here and never
change at runtime, which matches Prometheus client expectations (label
sets are bound at definition).

Counter naming follows the Prometheus convention: snake_case, suffix
with `_total` for counters, no unit suffix on gauges since the gauge
names already describe what they hold.
"""

from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge, generate_latest

# Re-exported so the /metrics router doesn't have to import prometheus directly.
__all__ = ["CONTENT_TYPE_LATEST", "REGISTRY", "metrics", "generate_latest"]


class _Metrics:
    """Container so call sites use one import and don't trip on module
    re-imports during pytest (Counter() raises on duplicate registration).
    """

    sessions_created_total = Counter(
        "sessions_created_total",
        "Sessions minted via POST /api/session or /demo.",
        ["is_demo", "provider"],
    )

    sessions_evicted_total = Counter(
        "sessions_evicted_total",
        "Sessions removed from the in-memory store, by cause.",
        ["reason"],  # idle | absolute_cap | explicit_delete
    )

    rate_limit_hits_total = Counter(
        "rate_limit_hits_total",
        "429 responses emitted by RateLimitMiddleware, by scope.",
        ["scope"],
    )

    provider_validation_failures_total = Counter(
        "provider_validation_failures_total",
        "Failures during POST /api/session key validation.",
        ["provider", "error_code"],
    )

    agent_guardrail_trips_total = Counter(
        "agent_guardrail_trips_total",
        "Agent loop hit a guardrail and stopped early.",
        ["type"],  # max_tool_calls | max_duration | max_input_length
    )

    insights_generated_total = Counter(
        "insights_generated_total",
        "Insights produced by a generator run, by card type.",
        ["card_type"],
    )

    demo_session_active = Gauge(
        "demo_session_active",
        "Demo sessions currently held in memory.",
    )


metrics = _Metrics()
