# YNAB Insights

An AI financial coach that lives alongside YNAB. Pulls your YNAB data into
a local Postgres, then surfaces a feed of forward-looking cards — recurring
subscriptions, week-over-week spending anomalies, 90-day cashflow forecasts,
goal trajectories, year-over-year category drift, and quarterly / annual
retrospectives. A Claude-backed agent (`Ask`) answers follow-up questions
with a streaming tool-use loop against the same database.

Self-hosted, single-user, exposed only over Tailscale.

## Stack

FastAPI + SQLAlchemy + Postgres on the backend. Next.js 15 (App Router) +
Tailwind + shadcn/ui + Tremor + Framer Motion on the frontend. Claude
(`claude-haiku-4-5`) for tool-use and the optional narrative pass on each
card. APScheduler runs sync and insight generators out of band.

## Local development

```bash
cp infra/compose/dev/.env.example infra/compose/dev/.env
# Fill in optional YNAB_TOKEN, ANTHROPIC_API_KEY.
docker compose -f infra/compose/dev/docker-compose.yml up
```

Frontend at <http://localhost:3000>. FastAPI at <http://localhost:8000>.
Both hot-reload on source changes.

Backend-only loop (no Docker, no frontend):

```bash
cd ynab_insights
pip install -e ".[dev]"
pytest
```

## Architecture

- `app/` — FastAPI service.
- `app/insights/` — Generator framework + one module per card type. Each
  generator is auto-registered on import and runs on its own APScheduler
  cadence.
- `app/services/queries.py` — Read aggregations matching YNAB's Income vs
  Expense semantics (net per category, RTA recognized as income,
  transfers to off-budget accounts kept as spending, closed accounts
  included).
- `frontend/app/insights/` — Feed + per-card detail routes.
- `frontend/app/reports/` — Row-for-row diff against YNAB's CSV when the
  dashboard totals don't agree.

Design notes — including all the heuristics, thresholds, and the v2.4
visual decisions — live in [`DESIGN.md`](DESIGN.md). Deployment notes:
[`../docs/deployment.md`](../docs/deployment.md).
