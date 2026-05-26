"""Insights Feed package.

Importing this package registers every generator with the registry in
`app.insights.base`. The orchestrator and the API endpoints iterate the
registry to discover what to run and how to dispatch generate-on-demand
requests.
"""

from __future__ import annotations

# Side-effect imports: importing each generator module triggers the
# @register_generator decorator at class-definition time, populating the
# registry in app.insights.base.
from app.insights import cashflow_forecast as _cashflow_forecast  # noqa: F401
from app.insights import category_drift as _category_drift  # noqa: F401
from app.insights import category_projection as _category_projection  # noqa: F401
from app.insights import goal_trajectory as _goal_trajectory  # noqa: F401
from app.insights import spending_anomaly as _spending_anomaly  # noqa: F401
from app.insights import subscription_audit as _subscription_audit  # noqa: F401
from app.insights import year_in_money as _year_in_money  # noqa: F401

# Public surface re-exported so callers can `from app.insights import ...`.
from app.insights.base import (
    GeneratedInsight,
    InsightGenerator,
    all_generators,
    get_generator,
    register_generator,
    run_all_generators,
)

__all__ = [
    "GeneratedInsight",
    "InsightGenerator",
    "all_generators",
    "get_generator",
    "register_generator",
    "run_all_generators",
]
