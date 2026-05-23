"""Insights Feed package.

Importing this package registers every generator with the registry in
`app.insights.base`. The orchestrator and the API endpoints iterate the
registry to discover what to run and how to dispatch generate-on-demand
requests.
"""

from __future__ import annotations

# Re-export the public surface so callers can `from app.insights import ...`.
from app.insights.base import (
    GeneratedInsight,
    InsightGenerator,
    RunOutcome,
    all_generators,
    execute_generator,
    get_generator,
    register_generator,
)

# Importing each generator module triggers the @register_generator decorator at
# class-definition time. Keep these imports at the bottom so the framework's
# public surface remains importable even if a generator import fails.
from app.insights import (  # noqa: E402, F401  (side-effect imports)
    cashflow_forecast,
    goal_trajectory,
    spending_anomaly,
    subscription_audit,
)

__all__ = [
    "GeneratedInsight",
    "InsightGenerator",
    "RunOutcome",
    "all_generators",
    "execute_generator",
    "get_generator",
    "register_generator",
]
