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
orchestrator (`run_all_generators`) owns the writes.

Concurrent generation (v2.6f). `run_all_generators` fans every
registered generator out to `asyncio.gather`, each wrapped in
`asyncio.wait_for(timeout=30s)`. A timed-out or raising generator
records a `RunRecord(status='error')` and does not block the others.
Id allocation stays sequential in the merge phase so concurrent
generators can't collide on the upsert map. Generators each own a
disjoint `card_type`, so their `dedup_key` sets never overlap.

The `/api/insights/generate` router writes the merged insights back to
`session.insights` and appends the new `RunRecord`s to `session.runs`.

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

Six generators ship today. Three of them (Spending Anomaly, Category
Drift, plus the cycle classifier they share) lean on
`app/snapshot/cycle.py:classify_category_cycle`, which decides whether a
category is `weekly | monthly | quarterly | annual | irregular` based
on transaction-interval shape in the trailing 12 months (18 for the
annual fallback). `irregular` is the fail-safe default; generators
that don't have a comparison window they trust will skip the category
rather than fire a low-confidence card.

- **Subscription Audit** (weekly): cluster recurring same-payee charges
  over a 365-day lookback. v2.6f normalizes payee names (strip case,
  punctuation, suffix tokens `INC`/`LLC`/`COM`/`PAYPAL *`, trailing
  transaction-id-shaped suffixes) before grouping, so "NETFLIX 4839A2NX"
  and "Netflix" cluster together. Amounts qualify within +/-12% of the
  cluster median (handles mid-window price changes). Minimum occurrences
  is 3 by default, or 2 if the single interval lands within +/-3 days
  of the canonical target for its cadence. Per-cadence interval bands:
  weekly 5-9d, monthly 25-35d, quarterly 75-105d, yearly 335-395d.
- **Spending Anomaly** (weekly): cycle-aware. Weekly-cycle categories
  compare current week vs trailing 12 weeks; monthly-cycle compare
  current month vs trailing 12 months. Quarterly/annual/irregular are
  skipped (Category Drift owns the comparison logic where it applies).
  Threshold: |z| >= 1.5 AND $50 absolute deviation. `cycle` discriminator
  in the structured payload tells the frontend which copy to render.
- **Cashflow Forecast** (daily): mean daily net over the last 90 days,
  projected 30/60/90 against today's CASH balance only (checking +
  savings + cash account types). Credit-card balances are surfaced as
  a separate `credit_card_debt_cents` context line — netting them
  against cash makes revolved credit look like a hole in the user's
  position when it isn't. Cash account types: `checking`, `savings`,
  `cash`. Credit types treated as debt: `creditCard`, `lineOfCredit`.
- **Goal Trajectory** (daily): per-goal projection from YNAB's
  `goal_months_to_budget` + `goal_overall_left`.
- **Category Drift** (monthly): comparison kind depends on the
  category's cycle. Monthly/quarterly cycles: trailing 3 months vs prior
  9 months (quarter-over-quarter). Annual cycles with at least 15 months
  of data: trailing 3 months vs the same 3 months one year prior
  (year-over-year), so tax prep / holiday spending / school supplies
  don't fire false drift cards. Categories with <12 months of activity
  or `irregular` cycle are skipped. Floors hold at +/-15% pct and
  $50/mo. `comparison_kind` discriminator in the structured payload.
- **Year in Money** (on-demand): no calendar gate. Annual variant when
  the snapshot spans >= 365 days, quarterly when it spans >= 90 days,
  no card under 90. Window always ends today; the dedup key buckets on
  `(kind, end-month)` so the card refreshes once per month at most.
  LLM writes the narrative; deterministic fallback paragraph.

**Fail-closed on LLM steps.** Where deterministic detection has an
LLM-aided fallback, the LLM-aided step never produces a low-confidence
card — on timeout, parse error, or no-key, the generator either skips
the category or falls back to the deterministic title/summary. The
feed staying quiet on hard-to-classify data is the goal; bad cards are
worse than missing cards.

Heuristic detail and dedup keys live in
[`../docs/ynab-insights.md`](../docs/ynab-insights.md).

## Rate limits + guardrails

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

## Provider abstraction (v2.6d)

`app/llm/` exposes an `LlmProvider` ABC plus per-vendor concrete classes
(`AnthropicProvider`, `OpenAIProvider`). The SSE wire format on `/ask`
doesn't depend on the provider; each provider normalizes its native
events into one of: `TokenEvent`, `ToolUseEvent`, `ToolResultEvent`,
`DoneEvent`, `ErrorEvent`. The agent loop just yields events to SSE.

Routing is by key prefix in `app/llm/detect.py`: `sk-ant-…` → Anthropic,
`sk-(proj-)?…` → OpenAI. Anthropic is checked first so the looser
OpenAI regex doesn't eat its keys. Per-provider model allow-lists
guard against typo'd or removed model IDs reaching the SDK.

Each provider owns the full tool-use loop (not just one turn). Callers
supply a `tool_dispatcher` callback that maps `(tool_name, input)` to
`(output, is_error)`; the provider pushes results back in its native
message shape (Anthropic `tool_result` content blocks vs OpenAI
`role:"tool"` messages).

## Demo mode (v2.6d)

`app/demo/` builds a deterministic `YnabSnapshot` for ~14 months of
fictional activity and one hand-written insight per card type. `POST
/api/session/demo` mints a real session with `is_demo=True` and the
pre-loaded data. No tokens, no upstream calls.

Behavior gates on `session.is_demo`:
- `POST /ask` → 403 with `{"error":"demo_mode_ask_disabled"}`.
- `POST /api/insights/generate` → no-op, returns `{"run_ids":[]}`.
- `POST /api/session/refresh` → just bumps `last_active_at`.

The deterministic snapshot doubles as fixture data: anyone reading the
codebase can `build_demo_snapshot()` in a test and exercise generator
logic without mocking YNAB.

## Public release defensive layers (v2.6e)

Three layers in front of the public deploy at https://ynab.majed.fyi.
All off by default; on for stage + prod via env injection in the deploy
workflows.

**Demo rate limit.** `POST /api/session/demo` is the only pre-auth
endpoint that mints state; cap at 10/hr per IP, configurable via
`DEMO_SESSION_RATE_LIMIT_PER_IP_PER_HOUR`. Same `_Rule` table as the
rest; scope `demo_session_create`.

**Proxy-header guard.** The Cloudflare Tunnel sets
`X-Forwarded-Proto: https`; the session cookie's Secure flag depends
on it. When `REQUIRE_PROXY_HEADERS=true`, `ProxyHeaderMiddleware` logs
one warning per minute per path if a request arrives without the
header. Does not reject. Catches tunnel misconfigs without breaking
the user-facing surface.

**Metrics token gate.** `GET /metrics` returns Prometheus text
exposition when `X-Admin-Token` matches `METRICS_ADMIN_TOKEN`.
**Returns 404 (not 401) when the token is wrong or the env var is
unset entirely** — scanners get the same response either way, so the
endpoint is indistinguishable from a non-existent route. Counters and
gauges cover sessions created/evicted, rate-limit hits, provider
validation failures, agent guardrail trips, insights generated, and
demo-session-active gauge. See `app/observability.py`.

`/metrics` is **not exposed publicly.** The Cloudflare Tunnel routes
the public hostname to the Next.js frontend container, which has no
`/metrics` route of its own (the catch-all proxy only forwards
`/api/*`). Scraping the public URL hits Next's own 404 before
reaching FastAPI. Read counters by execing into the app container
on the VM:

```bash
ssh deploy@<VM>
cd /home/deploy/stacks/prod  # or stage
docker compose exec app python -c "
import os, urllib.request
req = urllib.request.Request(
    'http://localhost:8000/metrics',
    headers={'X-Admin-Token': os.environ['METRICS_ADMIN_TOKEN']},
)
print(urllib.request.urlopen(req).read().decode())
"
```

The token lives in the container's env from the deploy step; no need
to pass it manually. If a future Grafana / Prometheus instance lives
on the tailnet, point its scraper at the FastAPI service's tailscale
IP (still not through CF) with the same token header.

## Deployment

Branch-to-env: `main` auto-deploys stage; prod redeploys on manual
`workflow_dispatch`. Builds two images (backend + frontend), pushes to
ghcr.io, scp the compose file to the VM over Tailscale, runs
`docker compose pull && up -d --remove-orphans`, smoke-checks `/health`.

Required env vars per stack:
- `SESSION_SECRET_KEY` — signs the cookie. Required (compose `?` syntax).
- `ANTHROPIC_MODEL` — default model when the user doesn't pick one.
- `REQUIRE_PROXY_HEADERS=true` — set on stage + prod, off in dev.
- `METRICS_ADMIN_TOKEN` — set from GitHub Secrets via the deploy step;
  unset means `/metrics` returns 404.

No database credentials, no provider tokens.

Full design in [`../docs/deployment.md`](../docs/deployment.md).
