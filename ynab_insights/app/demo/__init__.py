"""Demo mode: deterministic sample data for unauthenticated visitors.

`build_demo_snapshot()` returns a fully-shaped `YnabSnapshot` representing
a fictional ~mid-career person ("Alex") with 14 months of activity.
`build_demo_insights(snapshot)` returns one pre-baked Insight per card type.

Demo sessions skip token validation entirely: there are no tokens, no
upstream calls, no LLM cost. The cards use hand-written fallback copy
(`llm_enhanced=False`).
"""

from app.demo.insights import build_demo_insights
from app.demo.snapshot import build_demo_snapshot

__all__ = ["build_demo_insights", "build_demo_snapshot"]
