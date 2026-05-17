"""In-memory counters incremented from the request/loop paths and rendered
by the /metrics endpoint. Reset on process restart; that's acceptable for
a single-instance homelab. Wiring a real Prometheus pushgateway or scrape
target is a future enhancement."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Counters:
    sync_runs: int = 0
    sync_failures: int = 0
    ask_calls: int = 0
    ask_failures: int = 0
    tool_errors: int = 0


# Single module-level instance. Modules that need to increment import this.
counters = Counters()


def render_prometheus(
    counters: Counters,
    gauges: dict[str, int],
) -> str:
    """Render counters + gauges in Prometheus text exposition format."""
    lines: list[str] = []

    def counter(name: str, description: str, value: int) -> None:
        lines.append(f"# HELP {name} {description}")
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {value}")

    def gauge(name: str, description: str, value: int) -> None:
        lines.append(f"# HELP {name} {description}")
        lines.append(f"# TYPE {name} gauge")
        lines.append(f"{name} {value}")

    counter("ynab_insights_sync_runs_total", "Total sync runs that completed", counters.sync_runs)
    counter(
        "ynab_insights_sync_failures_total",
        "Total sync runs that failed with an exception",
        counters.sync_failures,
    )
    counter("ynab_insights_ask_calls_total", "Total /ask invocations", counters.ask_calls)
    counter(
        "ynab_insights_ask_failures_total",
        "Total /ask invocations that raised",
        counters.ask_failures,
    )
    counter(
        "ynab_insights_tool_errors_total",
        "Total agent tool executions that errored",
        counters.tool_errors,
    )

    for table, count in gauges.items():
        gauge(
            f"ynab_insights_{table}_rows",
            f"Row count in the {table} table",
            count,
        )

    return "\n".join(lines) + "\n"
