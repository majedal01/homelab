# YNAB Insights

An AI financial coach that lives alongside YNAB. Bring your own YNAB token and Anthropic key. Sign in, pick a budget, get a feed of forward-looking cards: recurring subscriptions, weekly spending anomalies, 90-day cashflow forecasts, goal trajectories, year-over-year category drift, and quarterly/annual retrospectives. A Claude-backed agent (`Ask`) answers follow-up questions with a streaming tool-use loop against the same in-memory snapshot.

**Zero persistence.** Tokens and your YNAB data live in server memory only. No database. Restart wipes everything. One-hour idle / four-hour absolute session cap.

## Stack

FastAPI + Pydantic on the backend, no database. `cachetools.TTLCache` holds sessions; `itsdangerous` signs the cookie. Next.js 15 (App Router) + Tailwind + shadcn/ui + Tremor + Framer Motion on the frontend. Claude (`claude-haiku-4-5`) for tool-use and optional narrative copy on each card.

## Local development

```bash
cp infra/compose/dev/.env.example infra/compose/dev/.env  # first time only
docker compose -f infra/compose/dev/docker-compose.yml up
```

Frontend at <http://localhost:3000>. FastAPI at <http://localhost:8000>. Both hot-reload on source changes.

Backend-only loop (no Docker, no frontend):

```bash
cd ynab_insights
pip install -e ".[dev]"
pytest
```

## Architecture

- `app/`: FastAPI service.
- `app/session/`: TTLCache session store, signed-cookie middleware, rate-limit middleware.
- `app/snapshot/`: in-memory data shapes and pure-Python aggregations (replaces SQLAlchemy).
- `app/insights/`: generator framework plus one module per card type. Each generator auto-registers on import.
- `app/agent/`: streaming Claude tool-use loop with per-request key, 20-tool-call cap, 60s wall-clock cap.
- `frontend/app/welcome/`: onboarding flow (token entry + budget picker).
- `frontend/app/insights/`: feed + per-card detail routes.
- `frontend/app/settings/`: refresh, end session, privacy notice.

Design notes (heuristics, thresholds, data model, session lifecycle, rate-limit numbers) in [`DESIGN.md`](DESIGN.md). The v2.5 planning doc with the rationale lives at [`../docs/ynab-insights.md`](../docs/ynab-insights.md). Deployment in [`../docs/deployment.md`](../docs/deployment.md).
