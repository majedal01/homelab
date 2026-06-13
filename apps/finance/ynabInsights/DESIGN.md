# YNAB Insights design notes

Architectural choices that span backend, frontend, and infra. Per-phase scope lives in
merged PR descriptions; this file is the load-bearing reference.

The app is multi-tenant and zero-persistence: no database, no background jobs. Users bring
their own YNAB and Anthropic keys; the server holds them in a TTL-evicted in-memory cache
for at most four hours. Restart wipes everything.

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

Browser only sees Next.js. FastAPI has no host port; the only reachable ingress is the
catch-all `/api/[...path]` proxy in Next, plus `/api/ask` with its own streaming-aware
handler. Both proxies forward the signed `sid` cookie up and Set-Cookie back down.

Stage and prod are two Compose stacks on one VM at ports 8001 and 8002. Deployment in
[`../../../docs/deployment.md`](../../../docs/deployment.md).

## Session model

One `UserSession` per signed-in user, held in a `cachetools.TTLCache` keyed by a UUID4
`sid`. The `sid` lives in a signed (itsdangerous) HttpOnly + Secure + SameSite=Strict
cookie. Idle TTL 1h; absolute cap 4h.

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

`TTLCache(maxsize=500, ttl=3600)` caps memory at roughly 5-10 MB per session. Single uvicorn
worker; horizontal scaling would need Redis.

## In-memory data layer

`app/snapshot/models.py` defines one budget's data (`YnabSnapshot` with accounts, categories,
payees, transactions). `app/snapshot/queries.py` holds pure-Python aggregations that replace
the deleted SQLAlchemy queries:

- `spending_by_category(snapshot, start, end)` -> category spend, most-negative first
- `period_summary(snapshot, start, end)` -> YNAB-style Income vs Expense rollup
- `category_monthly_history(snapshot, months)` -> per-category monthly net series
- `transactions_in_range(snapshot, df, dt)` -> ordered slice
- `starting_balance_cents(snapshot)` -> sum of open on-budget accounts

Semantics match the deleted SQL: positives in null-category or RTA are income; everything
categorized except RTA is spending; transfers between two on-budget accounts are excluded;
closed accounts stay in historical aggregates. A year of transactions (~3-8k rows) aggregates
in single-digit milliseconds; no indexing needed.

## Generator pattern

Each card type is one class subclassing `InsightGenerator`. Importing the module registers
it. Adding a card type is a single file plus a side-effect import in
`app/insights/__init__.py`.

```python
class InsightGenerator(ABC):
    card_type: ClassVar[str]
    cadence: ClassVar[str]  # informational; generated on demand

    @abstractmethod
    async def run(
        self,
        snapshot: YnabSnapshot,
        anthropic_key: SecretStr | None,
    ) -> Sequence[GeneratedInsight]: ...
```

`GeneratedInsight` is a small dataclass: `dedup_key`, `title`, `summary`, `structured_data`,
`llm_enhanced`. Generators are side-effect-free; the orchestrator (`run_all_generators`) owns
the writes.

Concurrent generation: `run_all_generators` fans every registered generator out to
`asyncio.gather`, each wrapped in `asyncio.wait_for(timeout=30s)`. A timed-out or raising
generator records a `RunRecord(status='error')` and does not block the others. Id allocation
stays sequential in the merge phase so concurrent generators cannot collide on the upsert map;
each owns a disjoint `card_type`, so their `dedup_key` sets never overlap.

## LLM degradation contract

Generators do deterministic Python for detection. The LLM is optional, runs after detection,
and can rewrite `title` and `summary`. Three guarantees:

- `anthropic_key` is `None` or whitespace-only: fallback copy. Card still renders.
- LLM call times out (5s) or raises: fallback. Run records `status='ok'`.
- LLM payload includes only the structured payload. No raw memos.

## Schemas

Discriminated union over the typed per-card payloads:

```python
InsightStructuredData = Annotated[
    SubscriptionAuditData | SpendingAnomalyData | CashflowForecastData
        | CategoryProjectionData | DebtPayoffData
        | GoalTrajectoryData | GoalSetupPromptData
        | CategoryDriftData | YearInMoneyData,
    Field(discriminator="card_type"),
]
```

OpenAPI emits `oneOf` with the discriminator hint; the frontend's hand-maintained
`lib/api-types.ts` mirrors the same union for clean TS discriminated-union matching.

## API surface

Session lifecycle:

- `POST   /api/session`         - validate tokens, return budget list, set signed cookie
- `POST   /api/session/budget`  - pick a budget, fetch its snapshot
- `GET    /api/session`         - metadata only (no tokens, no snapshot)
- `POST   /api/session/refresh` - re-fetch snapshot for active budget
- `DELETE /api/session`         - evict and clear cookie

Insights:

- `GET    /api/insights?card_type=&limit=20&offset=0`
- `GET    /api/insights/{id}`
- `POST   /api/insights/generate?card_type=` - run one or all
- `GET    /api/insights/runs?card_type=&limit=50`

Dismiss/restore endpoints are gone; dismissals live in browser localStorage keyed by
`dedup_key`.

Agent:

- `POST   /ask` - SSE; `{token, tool_use, tool_result, done, error}`.

## Card types

Eight generators ship. Detection is deterministic Python; cycle bands (`app/snapshot/cycle.py`)
classify each category's recurring cadence, and the anomaly and drift generators key off them.
A generator skips a category rather than fire a low-confidence card, and may emit more than one
`card_type` via the optional `GeneratedInsight.card_type` override (the orchestrator stamps it,
falling back to the registration slug).

- Subscription Audit: clusters recurring same-payee charges over a 365-day lookback,
  normalizing payee names and sub-clustering by amount so a price change splits cleanly. A
  signal gate (subscription/streaming/membership categories or a known-merchant allowlist)
  keeps it from surfacing every recurring charge.
- Spending Anomaly: cycle-aware. Weekly categories compare the current week to a trailing
  12-week window; monthly categories compare month-to-date to prior months' same-day-of-month
  windows. Quarterly, annual, and irregular are left to Category Drift.
- Cashflow Forecast: projects the 30/60/90-day cash position from mean daily net over 90 days.
  Credit-card balances surface as a separate debt line rather than netting against cash.
- Category Projection: month-end projection for the top trailing spenders from current pace
  versus a trailing-12-month baseline; skips the first days of the month when pace is noisy.
- Debt Payoff: payoff date per open credit/LoC account at the current paydown pace; skips
  growing balances and 10-year-plus projections.
- Goals (inferred progress): derives `emergency_fund_coverage` and `savings_rate_trend` from
  data always in the snapshot instead of relying on configured YNAB targets, and falls back to
  one `goal_setup_prompt` card when neither can be computed.
- Category Drift: quarter-over-quarter for monthly and quarterly cycles, year-over-year for
  annual cycles with enough history, so seasonal categories do not fire false drift.
- Year in Money: annual or quarterly retrospective with no calendar gate. The LLM writes the
  narrative with a deterministic fallback; top payees rank by net outflow.

Fail-closed on LLM steps. Where deterministic detection has an LLM-aided step, that step never
produces a low-confidence card: on timeout, parse error, or no key, the generator skips the
category or falls back to deterministic copy. A quiet feed on hard-to-classify data is the
goal; bad cards are worse than missing cards.

## Diagnostic logging

`LOG_GENERATOR_INTERNALS=true` turns on per-step INFO logging in every generator: a `start`
line with input counts, a `rejected`/`skipped` line per filter step with reason and count, and
a `finished` line with `insights_emitted`. Default silent so prod logs stay clean. The helper
lives in `app/insights/diagnostics.py` under logger `app.insights.diagnostics` for easy
filtering. Field values must be safe to log (no payee names, no raw amounts).

## Rate limits and guardrails

Per-session token-bucket middleware (`app/session/rate_limit.py`):

| Endpoint group | Limit | Bucket |
| --- | --- | --- |
| `POST /api/session/demo` | 10/hr | IP |
| `POST /api/session` | 5/hr | IP |
| `POST /api/session/budget` + `/refresh` | 10/hr | session |
| `POST /api/insights/generate` | 10/hr | session |
| `POST /ask` | 20/hr | session |
| `GET /api/*` reads | 120/min | session |

429 body: `{"error":"rate_limited","scope":...,"retry_after_seconds":N}`.

Agent loop guardrails (constants in `app/config.py`): 20 tool calls max, 60s wall-clock max
(`asyncio.wait_for`), 1000-char question max. Worst case per session per hour is roughly
20 asks times 20 tool calls times ~3k tokens, about $2 at Haiku rates.

## Frontend conventions

- TypeScript strict. Types in `lib/api-types.ts` mirror Pydantic responses by hand; CI guards
  drift via the `next build` typecheck.
- RSC server-side fetch forwards the request's `sid` cookie to FastAPI. Browser calls hit
  `/api/*`, which proxies to FastAPI internally.
- Dismissed insights live in `localStorage` keyed by `dedup_key`; the feed hydrates and filters
  at render time.
- A 401 on a protected route surfaces as `SessionExpiredError` from `apiFetch` and redirects to
  `/welcome?next=<path>`.

## Provider abstraction

`app/llm/` exposes an `LlmProvider` ABC plus per-vendor classes (`AnthropicProvider`,
`OpenAIProvider`). The SSE wire format on `/ask` does not depend on the provider; each
normalizes its native events into `TokenEvent`, `ToolUseEvent`, `ToolResultEvent`, `DoneEvent`,
or `ErrorEvent`. The agent loop yields events to SSE.

Routing is by key prefix in `app/llm/detect.py`: `sk-ant-…` to Anthropic, `sk-(proj-)?…` to
OpenAI. Anthropic is checked first so the looser OpenAI regex does not eat its keys.
Per-provider model allow-lists guard against typo'd or removed model IDs reaching the SDK. Each
provider owns the full tool-use loop (not one turn); callers supply a `tool_dispatcher`
callback mapping `(tool_name, input)` to `(output, is_error)`.

## Demo mode

`app/demo/` builds a deterministic `YnabSnapshot` for ~14 months of fictional activity and one
hand-written insight per card type. `POST /api/session/demo` mints a real session with
`is_demo=True` and the pre-loaded data. No tokens, no upstream calls. Behavior gates on
`session.is_demo`: `/ask` returns 403, `insights/generate` is a no-op, `session/refresh` only
bumps `last_active_at`. The deterministic snapshot doubles as fixture data for tests via
`build_demo_snapshot()`.

## Public release defensive layers

Three layers in front of the public deploy, off by default, on for stage and prod via
deploy-time env injection.

Demo rate limit. `POST /api/session/demo` is the only pre-auth endpoint that mints state;
capped per IP via `DEMO_SESSION_RATE_LIMIT_PER_IP_PER_HOUR`.

Proxy-header guard. The Cloudflare Tunnel sets `X-Forwarded-Proto: https`, which the cookie's
Secure flag depends on. With `REQUIRE_PROXY_HEADERS=true`, `ProxyHeaderMiddleware` logs one
warning per minute per path on a request that arrives without it. It does not reject.

Metrics token gate. `GET /metrics` returns Prometheus text when `X-Admin-Token` matches
`METRICS_ADMIN_TOKEN`, and 404 (not 401) when the token is wrong or unset, so the endpoint is
indistinguishable from a missing route. Counters live in `app/observability.py`.

`/metrics` is not exposed publicly: the Cloudflare Tunnel routes the public hostname to the
Next.js frontend, which has no `/metrics` route. Read counters from inside the VM:

```bash
ssh deploy@<VM>
cd /home/deploy/stacks/ynabinsights/prod  # or stage
docker compose exec app python -c "
import os, urllib.request
req = urllib.request.Request(
    'http://localhost:8000/metrics',
    headers={'X-Admin-Token': os.environ['METRICS_ADMIN_TOKEN']},
)
print(urllib.request.urlopen(req).read().decode())
"
```

## Deployment

Per-app workflows build the backend and frontend images, push to ghcr.io, and deploy the env's
compose stack over Tailscale with a `/health` check. Required env per stack:
`SESSION_SECRET_KEY` (signs the cookie, required), `ANTHROPIC_MODEL`, `REQUIRE_PROXY_HEADERS`
(on for stage and prod), `METRICS_ADMIN_TOKEN`. No database credentials, no provider tokens.
Full flow in [`../../../docs/deployment.md`](../../../docs/deployment.md).
