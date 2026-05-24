# YNAB Insights design notes (v2.5)

Architectural choices that span backend, frontend, and infra. Per-phase
scope lives in merged PR descriptions; this file is the load-bearing
reference. The deep planning rationale (session model, in-memory data
layer, dismissal pattern, rate limits, agent guardrails, validation
flow) lives in [`../docs/ynab-insights.md`](../docs/ynab-insights.md).

## What changed in v2.5

The app went from single-user with Postgres + scheduler to multi-tenant
zero-persistence. No database. No background jobs. Users bring their own
YNAB and Anthropic keys; the server holds them in a TTL-evicted in-memory
cache for at most four hours. Restart wipes everything.

## Architecture

```
browser  -->  :8001 / :8002  -->  frontend container (Next.js 15)
                                            |
                                            +-- /api/*  -> proxy route handler -+
                                                                                 \
                                            +-- RSC server-side fetch ----------> http://app:8000 (FastAPI)
                                                                                 /
                                                                         app container (in-memory only)
```

Browser only sees Next.js. FastAPI has no host port; the only reachable
ingress is via the catch-all `/api/[...path]` proxy in Next, plus
`/api/ask` which has its own streaming-aware handler. Both proxies forward
the signed `sid` cookie up and Set-Cookie back down.

Stage and prod are two Compose stacks on the same VM at ports 8001 and
8002. Deployment in [`../docs/deployment.md`](../docs/deployment.md).

## Session model

One `UserSession` per signed-in user, held in a `cachetools.TTLCache` keyed
by a UUID4 `sid`. The `sid` lives in a signed (itsdangerous) HttpOnly +
Secure + SameSite=Strict cookie. Idle TTL 1h; absolute cap 4h.

```python
class UserSession(BaseModel):
    sid: str
    ynab_token: SecretStr          # never serialized
    anthropic_key: SecretStr       # never serialized
    budget_id: str | None
    budget_name: str | None
    snapshot: YnabSnapshot | None
    insights: list[Insight]        # in-memory
    runs: list[RunRecord]          # in-memory
    created_at, last_active_at, last_synced_at: datetime
```

`cachetools.TTLCache(maxsize=500, ttl=3600)` caps memory at roughly
5-10 MB per session. Single uvicorn worker; horizontal scaling would
need Redis.

## In-memory data layer

`app/snapshot/models.py` defines the shape of one budget's data
(`YnabSnapshot` with accounts, categories, payees, transactions).
`app/snapshot/queries.py` holds pure-Python aggregations that replace
the deleted SQLAlchemy queries:

- `spending_by_category(snapshot, start, end)` -> list of category
  spend, most-negative first
- `period_summary(snapshot, start, end)` -> YNAB-style Income vs
  Expense rollup
- `category_monthly_history(snapshot, months)` -> per-category monthly
  net series
- `transactions_in_range(snapshot, df, dt)` -> ordered slice
- `starting_balance_cents(snapshot)` -> sum of open on-budget accounts

Semantics match the deleted SQL versions: positives in null-category
or RTA are income; everything categorized (except RTA) is spending;
transfers between two on-budget accounts are excluded; closed accounts
stay in historical aggregates.

A year of transactions (~3-8k rows) aggregates in single-digit
milliseconds; no indexing needed.

## Generator pattern

Each card type is one class subclassing `InsightGenerator`. Importing
the module registers it. Adding a new card type is a single file plus
a side-effect import in `app/insights/__init__.py`.

```python
class InsightGenerator(ABC):
    card_type: ClassVar[str]
    cadence: ClassVar[str]  # informational; v2.5 generates on demand

    @abstractmethod
    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
    ) -> Sequence[GeneratedInsight]: ...
```

`GeneratedInsight` is a small dataclass: `dedup_key`, `title`, `summary`,
`structured_data`, `llm_enhanced`. Generators are side-effect-free; the
orchestrator (`execute_generator`) owns the writes.

Orchestrator contract:

1. Receive `(generator_cls, snapshot, anthropic_key, next_id,
   next_run_id, existing)` where `existing` is a `(budget_id,
   dedup_key) -> Insight` map for upsert.
2. Call `generator.run(...)`. For each output, either insert with a
   fresh id or update the matching existing row in place (refreshed
   evidence, same id).
3. Return `(RunOutcome, updated_insights, RunRecord)`.

The `/api/insights/generate` router merges the returned insights back
into `session.insights` and appends the run to `session.runs`.

Exceptions are caught so one bad generator can't crash the endpoint.

## LLM degradation contract

Generators do deterministic Python for detection. The LLM is optional,
runs after detection, can rewrite `title` and `summary`. Three
guarantees:

- `anthropic_key` is `None` or whitespace-only: fallback copy. Card
  still renders.
- LLM call times out (5s) or raises: fallback. Run records `status='ok'`.
- LLM payload includes only the structured payload. No raw memos.

## Schemas

Discriminated union over the typed per-card payloads:

```python
InsightStructuredData = Annotated[
    SubscriptionAuditData | SpendingAnomalyData | CashflowForecastData
        | GoalTrajectoryData | CategoryDriftData | YearInMoneyData,
    Field(discriminator="card_type"),
]
```

OpenAPI emits `oneOf` with the discriminator hint; the frontend's
hand-maintained `lib/api-types.ts` mirrors the same union for clean TS
discriminated-union pattern matching.

## API surface

Session lifecycle:

- `POST   /api/session`         - validate tokens + return budget list,
                                   set signed cookie
- `POST   /api/session/budget`  - pick a budget, fetch its snapshot
- `GET    /api/session`         - metadata only (no tokens, no snapshot)
- `POST   /api/session/refresh` - re-fetch snapshot for active budget
- `DELETE /api/session`         - evict + clear cookie

Insights:

- `GET    /api/insights?card_type=&limit=20&offset=0`
- `GET    /api/insights/{id}`
- `POST   /api/insights/generate?card_type=` - run one or all
- `GET    /api/insights/runs?card_type=&limit=50`

Dismiss/restore endpoints are gone; dismissals live in browser
localStorage keyed by `dedup_key`.

Agent:

- `POST   /ask` - SSE; `{token, tool_use, tool_result, done, error}`.

## Card types

Six generators ship today, identical heuristics to v2.4:

- **Subscription Audit** (weekly): cluster recurring same-payee +
  same-amount charges over 90 days, classify by interval band.
- **Spending Anomaly** (weekly): z-score the current week against the
  12-week baseline per category, floor at $25 deviation.
- **Cashflow Forecast** (daily): mean daily net over the last 90 days,
  projected 30/60/90 against current open on-budget balance.
- **Goal Trajectory** (daily): per-goal projection from YNAB's
  `goal_months_to_budget` + `goal_overall_left`.
- **Category Drift** (monthly): trailing-quarter vs prior-three-quarters
  per-category, +/-15% pct and $50/mo floor.
- **Year in Money** (gates on Jan 1 / Apr 1 / Jul 1 / Oct 1): annual or
  quarterly retrospective; LLM writes the narrative, deterministic
  fallback paragraph.

Heuristic detail and dedup keys live in
[`../docs/ynab-insights.md`](../docs/ynab-insights.md).

## Rate limits + guardrails

Per-session token-bucket middleware (`app/session/rate_limit.py`):

| Endpoint group | Limit | Bucket |
| --- | --- | --- |
| `POST /api/session` | 5/hr | IP |
| `POST /api/session/budget` + `/refresh` | 10/hr | session |
| `POST /api/insights/generate` | 10/hr | session |
| `POST /ask` | 20/hr | session |
| `GET /api/*` reads | 120/min | session |

429 body: `{"error":"rate_limited","scope":...,"retry_after_seconds":N}`.

Agent loop guardrails (constants in `app/config.py`):

- 20 tool calls max
- 60s wall-clock max (`asyncio.wait_for`)
- 1000 char question max (Pydantic + router-level)

Worst case per session per hour: 20 asks * 20 tool calls * ~3k tokens
~ $2 at Haiku rates.

## Frontend conventions

- TypeScript strict. Types in `lib/api-types.ts` mirror Pydantic
  responses by hand; CI guards drift via `next build` typecheck.
- RSC server-side fetch forwards the request's `sid` cookie to FastAPI.
  Browser calls hit `/api/*` which proxies to FastAPI internally.
- Onboarding centered card with the aurora is the brand surface.
  Tailwind + shadcn/ui + Tremor + Framer Motion as in v2.4.
- Dismissed insights live in `localStorage` keyed by `dedup_key`;
  the feed hydrates and filters at render time.
- 401 on a protected route surfaces as `SessionExpiredError` from
  `apiFetch` and triggers a `next/navigation.redirect()` to
  `/welcome?next=<path>`.

## Deployment

Branch-to-env: `main` auto-deploys stage; prod redeploys on manual
`workflow_dispatch`. Builds two images (backend + frontend), pushes to
ghcr.io, scp the compose file to the VM over Tailscale, runs
`docker compose pull && up -d`, smoke-checks `/health`.

The only required env var per stack is `SESSION_SECRET_KEY` (used to
sign cookies). No database credentials, no provider tokens.

Full design in [`../docs/deployment.md`](../docs/deployment.md).
