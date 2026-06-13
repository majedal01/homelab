# YNAB Insights

**Live at [ynab.majed.fyi](https://ynab.majed.fyi).** Try the demo without signing up. Bring your own Anthropic or OpenAI key to use your real YNAB data.

An AI financial coach that lives alongside YNAB. Pick a budget, get a feed of forward-looking cards (recurring subscriptions, weekly spending anomalies, 90-day cashflow forecasts, goal trajectories, year-over-year category drift, quarterly/annual retrospectives). An agent (`Ask`) answers follow-up questions via your provider's streaming tool-use API against the same in-memory snapshot.

**Zero persistence.** Keys and YNAB data live in server memory only. No database. Restart wipes everything. One-hour idle / four-hour absolute session cap.

**Provider-agnostic.** Detect by key prefix at sign-in: `sk-ant-…` routes to Anthropic, `sk-…` (or `sk-proj-…`) routes to OpenAI. Both work for insight enhancement and the Ask tool-use loop. Model dropdown swaps tiles automatically.

**Demo mode.** No-key path for recruiters and the curious. A pre-baked deterministic snapshot and six hand-written insights covering every card type ship as a real (`is_demo=true`) session. `Ask` is disabled in demo with a clear sign-in CTA; everything else works.

## Stack

FastAPI + Pydantic on the backend, no database. `cachetools.TTLCache` holds sessions; `itsdangerous` signs the cookie. `prometheus-client` for the gated `/metrics` endpoint. Next.js 15 (App Router) + Tailwind + shadcn/ui + Tremor + Framer Motion on the frontend.

## Local development

```bash
cp apps/finance/deploy/dev/.env.example apps/finance/deploy/dev/.env  # first time only
docker compose -f apps/finance/deploy/dev/docker-compose.yml up
```

Frontend at <http://localhost:3000>. FastAPI at <http://localhost:8000>. Both hot-reload on source changes.

Backend-only loop (no Docker, no frontend):

```bash
cd apps/finance
pip install -e ".[dev]"
pytest
```

## Architecture

- `app/llm/`: provider abstraction. `LlmProvider` ABC + `AnthropicProvider` + `OpenAIProvider`. Normalized `StreamEvent` types so the SSE wire format stays stable across providers.
- `app/session/`: TTLCache session store, signed-cookie middleware, rate-limit middleware, proxy-header warn-on-missing middleware.
- `app/snapshot/`: in-memory data shapes and pure-Python aggregations (replaces SQLAlchemy).
- `app/insights/`: generator framework plus one module per card type. Each generator auto-registers on import.
- `app/demo/`: deterministic snapshot + hand-written insights for the no-key demo path.
- `app/agent/`: streaming agent loop with per-request key + provider. 20-tool-call cap, 60s wall-clock cap.
- `app/observability.py`: Prometheus counters + gauges, exposed at `GET /metrics` behind `X-Admin-Token`. Not public — the Cloudflare Tunnel only routes to Next.js, which has no `/metrics` route. Scrape from inside the VM (see "Operations" below).
- `frontend/app/welcome/`: onboarding (token entry + budget picker + demo CTA + provider auto-detect).
- `frontend/app/insights/`, `/explore/`, `/ask/`, `/settings/`.

Design notes (heuristics, thresholds, data model, session lifecycle, rate-limit numbers, provider abstraction, demo) in [`DESIGN.md`](DESIGN.md). Deployment in [`../../docs/deployment.md`](../../docs/deployment.md).

## Operations

**Read Prometheus metrics from the VM** (the token lives in the container's env, no need to pass it):

```bash
ssh deploy@<VM>
cd /home/deploy/stacks/finance/prod  # or stage
docker compose exec app python -c "
import os, urllib.request
req = urllib.request.Request(
    'http://localhost:8000/metrics',
    headers={'X-Admin-Token': os.environ['METRICS_ADMIN_TOKEN']},
)
print(urllib.request.urlopen(req).read().decode())
"
```

