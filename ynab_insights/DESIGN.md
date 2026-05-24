# YNAB Insights design notes

Architectural choices that span backend, frontend, and infra. Per-phase scope and rationale lives in merged PR descriptions; this file is the load-bearing reference.

## Architecture

```
browser -> :8001 / :8002 -> frontend container (Next.js 15)
                                |
                                +-- /api/ask  -> route handler ----+
                                                                    \
                                +-- RSC server-side fetch ---------> http://app:8000 (FastAPI)
                                                                    /
                                                            app container
```

Browser only ever sees Next.js. FastAPI is reachable only over the Compose-internal network; no host port. The single exception is `/api/ask`, a Next route handler that proxies SSE through to FastAPI so the client can show streaming state without CORS.

Stage and prod run as two isolated Compose stacks on the same VM, each with its own Postgres volume and host port (8001, 8002). See `docs/deployment.md`.

## Data model

Two tables drive the Insights Feed: `Insight` (what the user sees) and `InsightRun` (observability).

```python
class Insight(Base):
    id: int                       # serial
    budget_id: str (FK)
    card_type: str                # discriminator
    dedup_key: str                # unique with budget_id
    title: str
    summary: str
    structured_data: JSONB        # typed payload, varies by card_type
    generated_at: datetime
    refreshed_at: datetime
    dismissed_at: datetime | None # null = visible in feed
    llm_enhanced: bool            # observability

class InsightRun(Base):
    id: int                       # serial
    card_type: str
    started_at: datetime
    finished_at: datetime | None
    status: str                   # 'running' | 'ok' | 'error'
    duration_ms: int | None
    insights_created: int
    insights_updated: int
    error: str | None
```

Indexes:

- `(budget_id, dismissed_at, refreshed_at DESC)` on `Insight` for the feed query.
- Unique `(budget_id, dedup_key)` on `Insight` for idempotent upsert.
- `(card_type, started_at DESC)` on `InsightRun` for the runs page.

`Insight.structured_data` is JSONB on Postgres, TEXT-with-JSON on SQLite. SQLAlchemy's `JSON` type maps to both. The payload is typed via a Pydantic discriminated union (see "Schemas") so the frontend gets a clean TypeScript discriminated union via OpenAPI.

## Generator pattern

Each card type is one Python class subclassing `InsightGenerator`. Importing the module is enough to register it. Adding a new card type is a single file plus a side-effect import in `app/insights/__init__.py`.

```python
class InsightGenerator(ABC):
    card_type: ClassVar[str]            # discriminator, e.g. "subscription_audit"
    cadence: ClassVar[Cadence]          # scheduling hint

    @abstractmethod
    async def run(self, session, settings, budget_id) -> Sequence[GeneratedInsight]: ...
```

`GeneratedInsight` is a small dataclass: `dedup_key`, `title`, `summary`, `structured_data`, `llm_enhanced`. Generators are side-effect-free; the orchestrator does all writes.

The orchestrator (`app.insights.base.execute_generator`) is the only path that writes to `insights` or `insight_runs`:

1. Open an `InsightRun` row with `status='running'`, capture `started_at`.
2. Call `generator.run(...)`. For each `GeneratedInsight`, upsert by `(budget_id, dedup_key)`. New rows insert; existing rows update content in place (refreshed evidence, user's dismiss state preserved).
3. Close the run with terminal status, duration, counts, and any caught error.

Exceptions are caught so one bad generator can't crash the scheduler or the on-demand endpoint. Generators run via APScheduler on their declared cadence, or on demand via `POST /api/insights/generate`.

## LLM degradation contract

Generators do deterministic Python for detection. The LLM is optional, runs after detection succeeds, and can rewrite `title` and `summary` into warmer prose. Three guarantees:

- `ANTHROPIC_API_KEY` unset (or blank): generators use deterministic fallback copy. Card still renders.
- LLM call times out (5s) or raises: log, fall back to deterministic copy. Run records `status='ok'`.
- LLM payload includes only the structured payload. No raw memos, no unrelated transactions.

## Schemas

Discriminated union over the typed per-card payloads:

```python
class SubscriptionAuditData(BaseModel):
    card_type: Literal["subscription_audit"]
    payee_name: str
    cadence: Literal["weekly", "monthly", "quarterly", "yearly"]
    monthly_cost_cents: int
    annual_cost_cents: int
    occurrences: list[TransactionRef]

# ...one BaseModel per card_type...

InsightStructuredData = Annotated[
    SubscriptionAuditData | SpendingAnomalyData | CashflowForecastData
        | GoalTrajectoryData | CategoryDriftData | YearInMoneyData,
    Field(discriminator="card_type"),
]
```

Picked over per-type validators because it gives OpenAPI a `oneOf` with the discriminator hint, which `openapi-typescript` turns into a clean TS discriminated union the frontend switches on without casts.

## API surface

All under `/api/insights`:

- `GET    /api/insights?budget_id=&card_type=&include_dismissed=false&limit=20&offset=0` - feed query, newest first. Offset pagination; bounded volume so keyset isn't worth the complexity yet.
- `GET    /api/insights/{id}` - full payload with referenced transactions resolved server-side (no N+1 on the detail view).
- `POST   /api/insights/{id}/dismiss` - sets `dismissed_at`. Idempotent.
- `POST   /api/insights/{id}/restore` - clears `dismissed_at`. Backs the undo-toast on optimistic dismiss.
- `POST   /api/insights/generate?card_type=&budget_id=` - fire one generator or all. Returns the new `InsightRun` IDs.
- `GET    /api/insights/runs?card_type=&limit=50` - run observability.

## Card types

Six generators ship today. Each has deterministic detection, optional LLM enhancement, unit tests, a card component, and a detail route.

**Subscription Audit** (`subscription_audit`, weekly). Cluster recurring charges over the last 90 days by `(payee_id, amount_cents)`. Flag a cluster as a subscription when there are at least 3 occurrences inside a canonical-cadence tolerance (monthly 28-32d, weekly 6-8d, quarterly 85-95d, yearly 360-370d). Card highlights monthly cost; detail view shows all occurrences. Dedup key `subscription:{payee_id}:{amount_cents}:{cadence}`.

**Spending Anomaly** (`spending_anomaly`, weekly). For each spending category, take outflow per week across the trailing 13 weeks. Flag when `|z_score| >= 2.0` against the 12-week baseline AND absolute deviation is at least $25 (so a category that normally spends nothing doesn't fire on a single $5 charge). Dedup key `anomaly:{category_id}:{iso_year_week}`.

**Cashflow Forecast** (`cashflow_forecast`, daily). Mean daily net cashflow over the last 90 days, projected forward 90 days against current open on-budget balance. Card shows projected balance at +30/+60/+90. Detail view exposes top 5 categories with monthly averages so a what-if slider runs client-side. Dedup key `forecast:{budget_id}:{iso_year_week}` (refreshes weekly even though it runs daily).

**Goal Trajectory** (`goal_trajectory`, daily). For each Category with `goal_target_cents` set and `< 100%` complete: if the goal has a target date, project on-track vs behind via YNAB's `goal_months_to_budget`; if it's a target-balance goal, project completion date from current monthly contribution. Dedup key `goal:{category_id}:{iso_year_month}`.

**Category Drift** (`category_drift`, monthly). For each on-budget expense category, compare the trailing quarter's monthly average to the prior three quarters' average. Flag when `abs(drift_pct) >= 0.15 AND abs(drift_dollars) >= $50`. Both directions surface (upward drift = overspend; downward = freed up). Dedup key `drift:{category_id}:{year_month}`.

**Year in Money** (`year_in_money`, daily, but only emits on Jan 1 / Apr 1 / Jul 1 / Oct 1). Annual or quarterly retrospective. Python assembles the deterministic stats (income, spending, savings rate, top categories, top payees, biggest single transaction, savings-rate trend, largest category swing). The LLM writes the narrative; on failure the deterministic narrative ships. Dedup key `year_in_money:{budget_id}:{period_label}`.

## Scheduling

APScheduler runs alongside the existing sync job. Each generator has its own job; all are `coalesce=True, max_instances=1` so a slow run doesn't pile up. Default times follow the 30-minute sync so generators run against fresh data.

| Job | Cadence | Default time |
| --- | --- | --- |
| `insights_subscription_audit` | weekly | Mon 03:10 UTC |
| `insights_spending_anomaly`   | weekly | Mon 03:20 UTC |
| `insights_cashflow_forecast`  | daily  | 03:30 UTC |
| `insights_goal_trajectory`    | daily  | 03:40 UTC |
| `insights_category_drift`     | monthly | 1st 03:50 UTC |
| `insights_year_in_money`      | daily  | 04:00 UTC (gated on the period-start dates above) |

Setting `INSIGHTS_GENERATION_ENABLED=false` skips the cron jobs entirely; `POST /api/insights/generate` still works.

## Ask agent

`POST /ask` streams Server-Sent Events. Named events emitted in order:

- `event: token` - incremental answer chunks.
- `event: tool_use` - `{id, tool, input}` once the tool_use block finishes streaming.
- `event: tool_result` - `{id, output, is_error}` after the server runs the tool.
- `event: done` - `{turns_used, stop_reason}`.
- `event: error` - `{message}` on fatal mid-stream failure.

SSE over chunked HTTP or WebSocket: named events map cleanly to the three render concerns, the flow is one-way, and Next.js's route proxy replays it without buffering.

Cancellation: client aborts the fetch; FastAPI's async generator gets `CancelledError`, propagates it into Anthropic's streaming context so the SDK closes upstream and we stop being billed for unused tokens.

Conversation state is client-side only. Each request carries the full prior turns; backend has no session storage. Persisted to `sessionStorage` so refreshes survive but tab close clears it.

## Frontend conventions

- TypeScript strict. Response types generated from FastAPI's OpenAPI via `openapi-typescript` into `frontend/lib/api-types.ts`. CI fails on drift.
- Read paths use RSC + server-side fetch directly to `http://app:8000`. No TanStack Query / SWR; pages are read-heavy and URL search params hold filter state.
- shadcn/ui (slate) + Tailwind + Tremor for charts + Framer Motion. Motion tokens centralized in `frontend/lib/motion.ts`.
- Dark mode is class-strategy on `<html>`, persisted to `localStorage`, defaults to `prefers-color-scheme`.

## Deployment

Branch-to-env: `main` auto-deploys to stage; prod redeploys on manual `workflow_dispatch`. Both build versioned Docker images, push to ghcr.io, scp the compose file to the VM over Tailscale, run `docker compose pull && up -d`, smoke-check `/health`. Full design in [`../docs/deployment.md`](../docs/deployment.md).
