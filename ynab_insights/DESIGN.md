# YNAB Insights design notes

Cross-cutting decisions that span the app + infra. Phase-specific scope docs
live in `ynab_insights/README.md`; this file captures architectural choices
that recruiters and future-me will want to read in one place.

## v2.1 Frontend decisions

The Jinja2 + HTMX UI from Phase 3 is being replaced with a Next.js (App
Router) frontend. Background and choices.

### Why replace Jinja+HTMX

The HTMX UI proved the dashboard concept end-to-end and was a fast way to
ship Phase 3. For the portfolio framing, a TypeScript + React + Tailwind +
shadcn/ui stack is more legible to the audience (full-stack roles), easier
to extend with rich client behavior (streaming agent responses, tool-call
traces — both queued for later phases), and gives a clean separation
between the JSON API (FastAPI) and the presentation layer.

### Architecture

```
browser --> :8001/:8002 --> frontend container (Next.js)
                                    |
                                    +-- /api/ask  ---> route handler ---+
                                                                          \
                                    +-- RSC server-side fetch ----------> http://app:8000 (FastAPI)
                                                                          /
                                                                  app container
```

- The Compose stack gains a `frontend` service. Host port (8001/8002) now
  maps to the Next.js container's port 3000.
- FastAPI loses its host port mapping; only the frontend talks to it, over
  Docker's internal network at `http://app:8000`.
- Jinja templates, the `dashboard.py` HTML routes, and `templating.py` are
  removed at the end of the v2.1 PR. They remain in git history if needed.

### Data fetching: RSC + fetch, no client cache library

React Server Components fetch from FastAPI at render time. No TanStack
Query or SWR in v2.1. The pages are read-heavy; URL search params hold
filter state on the transactions page (shareable, navigable). The only
client-side mutation is the ask form, which posts to a Next.js route
handler that proxies to FastAPI.

If real-time updates or optimistic UI become a need in a later phase, we
can layer TanStack Query at that point without rewriting the RSC pages.

### API proxy boundary

Server components in the Next.js container fetch directly from
`http://app:8000` over Docker's compose network. The browser never sees
FastAPI's hostname or port.

The one exception is `/api/ask`: it's a client-initiated POST that needs
to show loading state, so the form posts to a Next.js route handler
(`app/api/ask/route.ts`) which forwards the request to FastAPI. This
keeps the browser's network calls relative-pathed.

### Type safety

TypeScript strict mode. Backend response types are generated from
FastAPI's OpenAPI schema via `openapi-typescript`, committed to
`frontend/lib/api-types.ts`. An `npm run generate-types` script
regenerates them; CI fails if the committed file is out of sync with the
backend's current OpenAPI output. No hand-rolled types for backend
responses.

### Component library

shadcn/ui with the `slate` color theme. Picked over zinc/stone/neutral
because slate reads slightly more saturated and "modern" in the same
neutral category. Defaults only in v2.1; visual polish and any custom
theming land in v2.2.

Components installed for parity with the current Jinja UI: button, card,
input, table, tabs, sheet, dialog, dropdown-menu, sonner, skeleton,
badge.

### Mobile nav

`Sheet` component (slides in from the side) on small viewports. Same nav
items as desktop, hidden behind a hamburger trigger.

### Dark mode

Class strategy (`class="dark"` on `<html>`), persisted to `localStorage`,
defaults to `prefers-color-scheme` on first visit. The toggle lives in
the top nav.

### CI

A new `.github/workflows/frontend-ci.yml` runs on changes to `ynab_insights/frontend/**`.
Steps: install (npm ci), lint (next lint), typecheck (tsc --noEmit),
build (next build), check that `lib/api-types.ts` is in sync with what
the generator would produce (fails if dirty).

The existing `ci.yml` (ruff/mypy/pytest) stays unchanged. Two separate
workflows because they need different runtimes and different path
triggers.

### Local development

A new `infra/compose/dev/docker-compose.yml` brings up all three services
locally with hot reload (frontend via `npm run dev`, FastAPI via
uvicorn's `--reload`, Postgres). `docker compose -f infra/compose/dev/docker-compose.yml up`
is the new entry point. Documented in the root `README.md`.

### File layout under `frontend/`

```
frontend/
├── app/                     # App Router pages
│   ├── layout.tsx           # root layout, theme provider, nav
│   ├── page.tsx             # / (dashboard)
│   ├── accounts/
│   │   ├── page.tsx         # /accounts
│   │   └── [id]/page.tsx    # /accounts/<id>
│   ├── transactions/page.tsx
│   ├── categories/page.tsx
│   ├── ask/page.tsx
│   ├── health/route.ts      # /health (frontend liveness)
│   └── api/
│       └── ask/route.ts     # /api/ask (proxy to FastAPI)
├── components/
│   ├── ui/                  # shadcn components
│   ├── nav.tsx              # top nav with mobile sheet
│   ├── theme-toggle.tsx
│   └── theme-provider.tsx
├── lib/
│   ├── api.ts               # `apiFetch()` helper
│   ├── api-types.ts         # generated from OpenAPI
│   └── utils.ts             # cn(), formatters
├── scripts/
│   └── generate-types.sh
├── public/
├── package.json
├── tsconfig.json
├── next.config.ts
├── tailwind.config.ts
├── postcss.config.mjs
└── components.json          # shadcn config
```

### Backwards compatibility and rollback

If something breaks in stage after the v2.1 deploy, rollback is one
manual `docker compose up -d` against the prior `stage-<sha>` images
(both `ynab_insights:stage-<prev>` and `ynab_insights_frontend:stage-<prev>`).
The dangling-image prune runs only AFTER the smoke check, so the
previous image is preserved until the next successful deploy.

The FastAPI JSON contracts on `/budgets`, `/accounts`, `/categories`,
`/payees`, `/transactions`, `/sync`, `/ask`, `/health`, `/metrics` are
unchanged; only the HTML-serving routes (`/`, `/categories/{id}`, and
the `_partials/*` endpoints) are removed.

## v2.2 Dashboard decisions

v2.1 shipped the Next.js scaffold with feature parity. v2.2 turns that
scaffold into something that reads like a finished product: KPI hero row,
trend chart, donut, data table, motion, real dark mode work.

### Libraries

- **Charts: Tremor v3 (`@tremor/react`)**. Built specifically for analytics
  dashboards, ships with sensible defaults for axis formatting, tooltips,
  and color palettes. Wraps Recharts under the hood. Tremor peer-deps on
  React 18 but works with React 19 in practice; install with
  `--legacy-peer-deps` to silence the warning. Frontend CI and the
  Dockerfile both pass this flag.
- **Motion: `motion`** (the new package name for the library formerly
  published as `framer-motion`). Used for staggered card entrance and
  hover lifts, not exuberant page transitions.
- **Data table: TanStack Table v8** (`@tanstack/react-table`) for the
  transactions page. Headless, server-friendly, integrates with shadcn's
  data-table pattern.
- **Date range picker: `react-day-picker` v9** (already shadcn's date
  primitive). Wrapped in a shared `<DateRangePicker>` component with
  presets and URL persistence.
- **Font: Inter via `next/font/google`** for body + UI, with tabular
  numerals enabled (`font-feature-settings: "tnum"`) on every numeric
  span via Tailwind's `tabular-nums` utility. No separate display font;
  Inter at larger sizes handles KPI numbers cleanly and avoids a second
  font download.

### KPI definitions

Documented here so the dashboard's numbers are reproducible and the
agent can answer "how is X calculated" with one source of truth.

- **Net Worth** — sum of `balance_cents` over all open accounts
  (`on_budget` ∪ tracking). Closed accounts excluded.
- **This Month Spending** — sum of `-amount_cents` over transactions
  where `amount_cents < 0`, the transaction's account is on-budget, the
  date falls in the current calendar month (1st → today), and
  `transfer_account_id IS NULL` (transfers are not spending). Displayed
  as a positive number.
- **This Month Income** — sum of `amount_cents` over transactions where
  `amount_cents > 0`, account is on-budget, date in current month, and
  not a transfer.
- **Income vs Spending** — surplus `income - spending` for the current
  month. Positive means living below means; negative means drawing
  down. Displayed with a sign.
- **Savings Rate** — `(income - spending) / income`, expressed as a
  percentage. If income is zero or negative, displayed as `—`.
- **vs Last Month** — every KPI shows a delta vs the same metric for the
  prior calendar month (same definition, shifted). Color: green when
  the delta improves the metric (income up, spending down, savings rate
  up); red when it worsens it; muted when zero or undefined.

### Date range

A single `<DateRangePicker>` lives in the page chrome wherever date
filtering applies (dashboard, transactions, categories). Presets:

- **This month** (default)
- **Last month**
- **This year**
- **Last 90 days**
- **Custom** (calendar)

State persists in URL search params (`date_from`, `date_to`) so back/
forward navigation and shareable links work. The dashboard's KPI row
ignores this picker — KPIs are intentionally always "this month vs last
month" so the hero row stays comparable across refreshes. The trend
chart and the category donut respect the picker.

### Color palette

Stays on shadcn `slate`. Semantic accents within Tailwind tokens:

- **Positive amounts / income** — `emerald-600` (light) / `emerald-400`
  (dark). Tabular-nums.
- **Negative amounts / spending / liabilities** — `--destructive`
  (already brightened in dark mode in v2.1.x to clear WCAG AA).
- **Net worth, trend chart fills** — `--primary`. Tremor's `indigo` and
  `slate` palette options are mapped to this via Tailwind tokens so
  Tremor charts inherit shadcn theming.

### Chart defaults

Tremor defaults are kept unless they actively hurt:

- BarChart and AreaChart use the `indigo` color category mapped to
  `--primary`. Y-axis formatter: short-form dollars (e.g. `$1.2K`,
  `$45K`).
- DonutChart variant is `donut` (not `pie`); category labels render in
  a side legend (Tremor's `<Legend>`), not inside the chart.
- No animation duration override — Tremor's default 900ms easeOut
  matches the rest of the entrance motion.

### Motion

Cards on the dashboard fade-and-slide in (`y: 8 → 0`, `opacity: 0 → 1`)
with a 60ms stagger between siblings. Triggered once on first mount via
`motion.div`. Hover lift is a 1px translate, no shadow — restrained.

Page transitions are not animated (they fight Next.js' default RSC
flow). Filter changes use `router.refresh()`; the resulting re-render
is smooth because RSC streams progressively.

### Skeletons + empty states

- **Skeletons**: page-level for now. Each page exports a `loading.tsx`
  that mirrors the final layout's card grid using `<Skeleton>`. KPI row
  is 4 boxes; chart placeholders are filled rectangles with the same
  aspect ratio as the live charts.
- **Empty states**: a small lucide icon + one-line copy + (optional)
  CTA link. Component lives at `frontend/components/empty.tsx`.

### Out of scope (kicked to v2.2.x or v2.3)

- Account-level 30-day sparkline. The backend doesn't store balance
  history (we sync current balance only); deriving it from transactions
  requires either a backfill aggregator or a `/reports/balance-history`
  endpoint. Deferred — accounts page keeps the current balance + type
  badge for v2.2.
- Category-level mini sparklines + progress bars against budgeted
  amounts. `/categories` doesn't currently return `budgeted_cents`;
  exposing it is straightforward but separate work. Categories page
  gets the polish pass minus the sparkline.

## v2.3 Agent UX decisions

v2.1 shipped a plain in/out form for `/ask`. v2.3 turns it into the demo
piece: streaming answers, a visible tool trace, multi-turn conversation
within a session, suggested questions on the empty state.

### Streaming protocol: SSE

The backend rewrites `POST /ask` to return `text/event-stream`. Named
events emitted in order:

- `event: token` — `data: <chunk>` — incremental answer text.
- `event: tool_use` — `data: {"id","tool","input"}` — assistant invoked
  a tool. Emitted when the tool_use block finishes streaming (so input
  is complete JSON), not on every partial JSON delta.
- `event: tool_result` — `data: {"id","output","is_error"}` — server ran
  the tool and is sending the result back to Claude.
- `event: done` — `data: {"turns_used","stop_reason"}` — final.
- `event: error` — `data: {"message"}` — fatal error mid-stream.

SSE picked over chunked HTTP and WebSocket because it has named events
(maps cleanly to `token` vs `tool_use` vs `tool_result`), is one-way
which matches the agent flow, replays cleanly through Next.js' route
proxy, and is supported by the Fetch streams API on the browser side
without extra libraries. WebSocket would add reconnection complexity
for no win; chunked HTTP would force the client to parse a custom
delimiter.

### Cancellation

Client aborts the `fetch()` with an `AbortController`. The TCP stream
closes; FastAPI's async generator gets cancelled (`asyncio.CancelledError`).
The generator must propagate that cancellation into the Anthropic
streaming context (`async with client.messages.stream(...)`) so the
SDK closes its connection upstream and the model stops generating
tokens we'd otherwise be billed for. The generator catches
`CancelledError`, closes the stream, and re-raises.

### Conversation context: session-only

Each frontend request includes `history`, the full prior turns as
Anthropic-format message dicts. Backend has no session storage; every
request is stateless. Frontend persists `history` to `sessionStorage`
so refreshes survive but tab close clears it. Aligns with the v2.4
"privacy by default" story — no per-user state on the server.

Context strategy: start with full history. If a user ever blows
through 200K tokens of conversation in one session, revisit with a
sliding window or summarization. Not building for that today.

### Tool trace UI

Inline above the answer, in the same chat bubble. Renders a "Tools
used" chip per call as it happens, animated entrance. Each chip
expands to show args (JSON, collapsed by default) and result (JSON,
collapsed). Tool calls remain visible for the lifetime of the answer;
the whole trace section is collapsible as a group via an action
button.

Inline placement chosen over sidebar because the trace IS the
"watching the agent think" moment; pushing it sideways hides the
narrative. Above the answer rather than below so it reads in temporal
order (tools called first, then synthesized answer).

### Markdown rendering

`react-markdown` + `remark-gfm`. Tables, lists, links, code spans. No
`rehype-raw` — we never want to render arbitrary HTML from the model.
react-markdown is safe by default (no `dangerouslySetInnerHTML`); we
verify by not enabling the unsafe plugin chain. Code blocks render as
`<pre><code>` without syntax highlighting; the agent answers about
budget data, not code, so a syntax-highlight dependency would be dead
weight. Add `rehype-highlight` later if a tool ever returns SQL in its
answer.

### Suggested questions

GET `/suggestions?budget_id=...` returns a small mixed list:

- 2-3 curated, hardcoded prompts that exercise different tools.
- 2-3 data-driven prompts derived from the user's actual data
  (top category in the latest sync, biggest single transaction
  recently, longest gap in spending). Built server-side so the
  frontend doesn't need to know the formulas.

Empty state renders these as chips; click pre-fills the input and
submits.

### Action buttons per answer

- Copy answer (markdown text) to clipboard.
- Regenerate (re-send same question + prior history).
- Show/hide tool trace toggle (the per-answer one, distinct from
  the per-call expand).

### Input

Auto-growing textarea, Cmd/Ctrl+Enter submits. Submit button shows
loading state during streaming; Cancel button appears in its place
once a stream is in flight. Disabled while streaming so the user
can't double-submit.

### Out of scope (deferred to v2.4 or beyond)

- BYOK / multi-tenant — v2.4.
- Cross-session persistence — intentionally never; conflicts with the
  privacy-by-default story.
- Voice or other modalities.
- Inline charts in answers (text only for now).

## v2.4 Insights Feed decisions

### Framing shift

Through v2.3 this app was framed as "an AI-augmented dashboard for YNAB."
v2.4 changes the framing to "the AI financial coach that lives alongside
your YNAB." YNAB plus its toolkit already covers the present and past
view of money. This app focuses on what they don't: forward-looking
analysis, pattern detection, and narrative coaching delivered as a feed
of digestible cards.

That framing has three concrete consequences:

1. The homepage is no longer a YNAB-shaped dashboard. It becomes the
   Insights Feed.
2. The top-level routes that duplicated YNAB's own UI (Dashboard,
   Accounts, Transactions, Categories) are removed entirely, along with
   their components. The underlying SQLAlchemy models stay — they power
   the generators and the per-card detail views — but there is no
   user-facing data browser.
3. The nav collapses to two surfaces: Insights (primary) and Ask
   (existing agent from v2.3).

### Generator pattern

Each card type is a Python class subclassing `InsightGenerator` and
auto-registered when its module is imported. The base class declares:

```python
class InsightGenerator(ABC):
    card_type: ClassVar[str]            # discriminator, e.g. "subscription_audit"
    cadence: ClassVar[Cadence]          # how often the scheduler runs it
    @abstractmethod
    async def run(self, session, settings, budget_id) -> list[GeneratedInsight]: ...
```

`GeneratedInsight` is a small dataclass with `dedup_key`, `title`,
`summary`, and `structured_data` (the typed payload that drives the
card UI). The registry is populated by a `@register_generator`
decorator. The orchestrator owns the database write path:

- Open an `InsightRun` row with `status='running'`, capture
  `started_at`, run the generator.
- For each `GeneratedInsight`, upsert by `(budget_id, dedup_key)`:
  insert if new; if a non-dismissed row with the same key already
  exists, update its content in-place (keeps the user's interaction
  state but lets new evidence refresh the card).
- Close the run with `status='ok' | 'error'`, `duration_ms`, error
  message, and the count of insights produced.

Generators never touch the request path. They run via APScheduler on
their declared cadence, or via the on-demand `POST /api/insights/generate`
endpoint, which dispatches each registered generator in a worker task
and returns immediately with the new `InsightRun` IDs.

### LLM use: hybrid, degradation-safe

Each generator does deterministic Python for detection and math. The
LLM is optional and runs *after* deterministic detection succeeds:
given the structured payload, it can rewrite `title` and `summary` into
warmer, human-tone copy. The LLM is not in the critical path:

- If `ANTHROPIC_API_KEY` is unset, generators run with their default
  templated copy. The card still renders.
- If the LLM call times out (5s default) or raises, generators log
  and fall back to the deterministic copy. The run still records
  `status='ok'`.
- LLM payloads send only the minimum needed fields: the structured
  payload itself, never raw memos or unrelated transaction context.

### Card types in this PR

Four generators ship together. Each has deterministic detection,
optional LLM enhancement, unit tests, a frontend card component, and a
detail view.

**Subscription Audit** — `card_type: "subscription_audit"`, cadence
weekly. Cluster recurring charges over the last 90 days by
`(payee_id, amount_cents)`. A cluster is "subscription-like" when:

- ≥3 occurrences within 90 days, AND
- the intervals between consecutive occurrences land within a tolerance
  of one of the canonical cadences (`monthly`: 28–32 days,
  `quarterly`: 85–95 days, `weekly`: 6–8 days, `yearly`: 360–370 days).

For each detected cluster, monthly cost = `amount_cents` converted to
the cluster's cadence (e.g. quarterly cost / 3). Card surfaces monthly
cost prominently, annual cost secondary, plus the list of detected
charges in the detail view. Dedup key:
`subscription:{payee_id}:{amount_cents}:{cadence}`.

**Spending Anomaly** — `card_type: "spending_anomaly"`, cadence weekly.
For each spending category, compute outflow per week over the trailing
13 weeks. The most recent week is the "current" week; the prior 12 are
the baseline. A category flags when:

- `|z_score| >= 2.0` against the baseline, AND
- the absolute deviation is at least `$25` so a category that normally
  spends nothing doesn't surface on a single $5 charge.

Card shows the category, the deviation (e.g. "+147% vs your 12-week
average"), and the top transactions driving the spike in the detail
view. Dedup key: `anomaly:{category_id}:{week_label}` where
`week_label` is the ISO year-week of the current week, so a fresh
anomaly each week dedupes cleanly.

**Cashflow Forecast** — `card_type: "cashflow_forecast"`, cadence
daily. Take the last 90 days of transactions, compute the mean daily
net cashflow (income − spending, transfers excluded), and project that
mean forward 90 days. Starting balance is the current sum of open
on-budget accounts. Card shows projected balance at +30/+60/+90 days.
The detail view holds the per-category breakdown and interactive
sliders for what-if scenarios — sliders are frontend-only; the
backend payload includes the top 5 spending categories with their
monthly average so the slider math runs client-side. Dedup key:
`forecast:{budget_id}:{iso_year_week}` so the card refreshes weekly
even though the generator runs daily.

**Goal Trajectory** — `card_type: "goal_trajectory"`, cadence daily.
This generator depends on YNAB goal data, which v2.4 starts persisting
on `Category`: `goal_type`, `goal_target_cents`, `goal_target_month`,
`goal_percentage_complete`, `goal_overall_left_cents`,
`goal_months_to_budget`. The sync pulls them through. For each
category with `goal_target_cents` set and `goal_percentage_complete <
100`:

- If `goal_type='TBD'` (target by date), project on-track vs behind
  using YNAB's `goal_months_to_budget` and `goal_overall_left`.
- If `goal_type='TB'` (target balance, no deadline), project completion
  date assuming the user keeps funding at the current monthly cadence
  (`goal_overall_left / monthly_contribution`).

Acceleration slider is frontend-only; backend exposes
`remaining_cents`, `current_monthly_contribution_cents`, and
`target_date` so the client can recompute. Dedup key:
`goal:{category_id}:{iso_year_month}` — one refreshed insight per goal
per month.

### Why the YNAB goal fields land in this PR

Without them the Goal Trajectory generator has no signal to project
against — transactions alone don't reveal which categories are goals.
Adding six nullable columns to `Category` plus extending the YNAB
client pydantic model and sync upsert keeps the change small. The new
fields default to `NULL` and don't affect any v2.1/v2.2/v2.3 behavior.

### Data model: `Insight` and `InsightRun`

```python
class Insight(Base):
    id: int                       # serial
    budget_id: str (FK)
    card_type: str                # discriminator
    dedup_key: str                # unique with budget_id
    title: str
    summary: str                  # short human-facing copy
    structured_data: JSONB        # typed payload, varies by card_type
    generated_at: datetime
    refreshed_at: datetime        # updated on re-upsert
    dismissed_at: datetime | None # null = visible in feed
    llm_enhanced: bool            # did the LLM rewrite this? observability

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

`Insight.structured_data` is JSONB on Postgres and TEXT-with-JSON on
SQLite. SQLAlchemy's `JSON` type maps to both. Indexes:

- `(budget_id, dismissed_at, refreshed_at DESC)` for the default feed
  query.
- Unique `(budget_id, dedup_key)` — idempotency.
- `(card_type, started_at DESC)` on `InsightRun` for the runs page.

### Pydantic schema: discriminated union

`structured_data` is typed end to end. Each card type has its own
schema:

```python
class SubscriptionAuditData(BaseModel):
    card_type: Literal["subscription_audit"]
    payee_name: str
    cadence: Literal["weekly", "monthly", "quarterly", "yearly"]
    monthly_cost_cents: int
    annual_cost_cents: int
    occurrences: list[OccurrenceRef]  # transaction IDs + dates + amounts

# ...one per card type...

InsightStructuredData = Annotated[
    SubscriptionAuditData | SpendingAnomalyData | CashflowForecastData
        | GoalTrajectoryData,
    Field(discriminator="card_type"),
]
```

Discriminated union (over per-type validators) because it gives
generated OpenAPI a `oneOf` with the discriminator hint, which
openapi-typescript turns into a clean TS discriminated union the
frontend can switch on without `as`-casts.

### API surface

- `GET /api/insights?budget_id=&include_dismissed=false&limit=20&offset=0`
  — feed query. Newest first. Default excludes dismissed.
- `GET /api/insights/{id}` — full payload including the transactions
  referenced in `structured_data` (resolved server-side so the detail
  view doesn't fan out into N+1 fetches).
- `POST /api/insights/{id}/dismiss` — sets `dismissed_at`. Idempotent.
- `POST /api/insights/generate?card_type=&budget_id=` — fire one or
  all generators on demand. Returns the new `InsightRun` IDs.
- `GET /api/insights/runs?limit=50` — last N runs across all card
  types for observability / debug.

### Scheduling

APScheduler gains four jobs alongside the existing sync job:

- `insights_subscription_audit` — weekly (Monday 03:10 UTC).
- `insights_spending_anomaly` — weekly (Monday 03:20 UTC).
- `insights_cashflow_forecast` — daily (03:30 UTC).
- `insights_goal_trajectory` — daily (03:40 UTC).

Cadence values are configurable via env vars (e.g.
`INSIGHTS_FORECAST_INTERVAL_HOURS`); the times above are defaults that
follow the existing 30-minute sync so generators always run against
fresh YNAB data. Each job is `coalesce=True, max_instances=1` so a slow
run doesn't pile up.

### Navigation consolidation

The pages removed in this PR:

- `/` (the v2.2 Dashboard) — replaced by an HTTP 307 redirect to
  `/insights`.
- `/accounts`, `/accounts/[id]`
- `/transactions`
- `/categories`

…along with their components (`dashboard/`, `accounts/`,
`transactions/`, `categories/` under `frontend/components/`) and the
shared utilities they pulled in: `lib/metrics.ts` (KPI math used only
by the dashboard) and `components/date-range-picker.tsx`. The picker
was originally going to stay for cashflow detail, but the v2.4 cashflow
detail uses a fixed 90-day lookback chosen by the backend, so the
picker has no consumer and is removed too. If a future detail view
needs interactive date selection, the picker comes back in that PR.

The nav becomes two items: **Insights** and **Ask**.

### Deep-dive UX: dedicated route, not side sheet

Clicking a card navigates to `/insights/[id]` — a full route, not a
side sheet. Reasons:

- Detail views can be dense (transaction tables, multi-card slider
  layouts) and a sheet feels cramped.
- A route URL is shareable and back/forward-navigable, which matches
  how the rest of the app uses RSC for read-heavy pages.
- The pre-loaded Ask context is a one-click handoff to `/ask`; the
  detail page can host that context cleanly without competing with a
  sheet's close affordance.

Each card type contributes one detail-page component selected by
`card_type`. The page also exposes a "Discuss in Ask" CTA that
navigates to `/ask?prefill=<question>` with the question seeded from
the insight's structured data (e.g. "Why has my Groceries spending
spiked 147% this week?"). The Ask page reads `prefill` from the URL on
mount and submits.

### Pagination

Server-side offset pagination on `GET /api/insights`. Default limit
20, max 100. Feed page renders with cursor links (`?offset=20`,
`?offset=40`). Offset is acceptable here because:

- Total insight count is bounded (a handful per generator per cadence
  cycle, dismissed and visible combined).
- The feed isn't a high-velocity stream where insert-during-paging
  would skew offsets meaningfully.

If volume ever becomes a problem the route can switch to keyset on
`(refreshed_at, id)` without a client-visible change.

### Out of scope (future PRs)

- Additional card types: Category Drift, Year-in-Money / Quarter-in-
  Money, What-If Scenario (agent-driven, generated on demand from
  Ask). Each is one-PR-per-card-type follow-up work.
- Severity-based ranking or curation of the feed.
- Per-card-type user preferences (snooze, mute, threshold tuning).
- Email digest, sharing, cancellation deep-links from Subscription
  Audit cards.

## v2.4 Polish + new card types

This phase continues the Insights Feed work. The previous PR shipped the
framework and four card types; this one adds two more (Category Drift,
Year in Money), takes the visual layer from "shadcn default" to "built",
and does a copy pass across the app and the docs.

### Visual identity

**Mark.** A "constellation" — 5–7 dots connected by hairline strokes,
asymmetric so it leans subtly forward. Single-stroke, `currentColor` so
it inherits text color and adapts cleanly across themes. Three lockups
ship: full (mark + wordmark side by side), mark-only (favicon, social
preview), wordmark-only (footer).

The reference set is Linear, Arc, and Vercel. The common thread:
restrained, geometric, no skeuomorphism, no gradient bling. The
constellation choice gives "insights" a small visual anchor (look up,
find patterns) without being literal about finance.

**Wordmark typography.** Geist (Vercel's typeface) — sans, geometric,
modern, free via Google Fonts. Falls back to Inter Display. Sentence
case ("YNAB Insights", not all-caps). Slightly tighter letter-spacing
than body text.

**Favicons.** Generated from the mark-only variant at 16/32/64/128/256.
The 16/32 versions need pixel-perfect tweaks (the hairlines disappear at
small sizes) so the favicon uses a stroke-widened version of the same
geometry.

### Aurora background

Three overlapping `radial-gradient` washes, each on its own absolutely-
positioned div with `filter: blur(140px)` and slow `transform: translate`
animation (40s+, easeInOut, infinite, alternating). The whole stack sits
inside a fixed-position container at `z-index: -1` so it never affects
layout or hit-testing.

**Palette** (dark mode primary, light mode fainter):

| Wash | Dark mode (rgba) | Light mode (rgba) |
| --- | --- | --- |
| Indigo  | `99 102 241 / 0.18` (`indigo-500`)  | `99 102 241 / 0.06` |
| Violet  | `139 92 246 / 0.14` (`violet-500`)  | `139 92 246 / 0.05` |
| Cyan    | `34 211 238 / 0.10` (`cyan-400`)    | `34 211 238 / 0.04` |

These three sit cleanly together because they all sit on the
indigo→cyan arc — a single-temperature palette reads "premium" instead
of "fruit basket". Background body color stays `bg-background`
underneath so the washes are additive, not dominant.

**Variants.**

- `<Aurora variant="primary" />` — feed page only.
- `<Aurora variant="quiet" />` — detail views and Ask; one wash, lower
  opacity, no motion (animation removed via `prefers-reduced-motion`
  too).
- Everywhere else: no aurora.

Performance is paid up-front: the gradients are GPU-composited and the
motion uses only `transform`, so paint cost stays at zero after first
render. No JavaScript involvement.

### Motion tokens

Centralized in `frontend/lib/motion.ts`. A single source of truth so
"feels too snappy" / "feels too sluggish" is a one-line change:

```ts
export const MOTION = {
  // Durations (ms)
  d: { instant: 120, fast: 200, base: 280, slow: 420, hero: 680 },
  // Easings
  e: {
    out: [0.16, 1, 0.3, 1],     // expo out — primary card/detail spring
    inOut: [0.4, 0, 0.2, 1],    // material standard
    spring: { type: "spring", stiffness: 380, damping: 32 },
  },
  // Stagger
  stagger: 0.05, // 50ms between siblings (card entrance)
} as const;
```

### Six interactions

1. **Page transitions.** Card → detail uses Framer Motion's `layoutId`
   to morph the card frame into the detail header. Spring physics
   (`MOTION.e.spring`).
2. **Card entrance stagger.** Cards fade-and-slide in (`y: 8 → 0`,
   `opacity: 0 → 1`) with `MOTION.stagger` between siblings, `MOTION.e.out`
   easing, `MOTION.d.base` duration. Triggered once on mount.
3. **Card hover.** 2px lift via `translate-y-0.5`, soft shadow expansion
   (`shadow-sm → shadow-md`), optional 1px primary-tinted border. No
   `scale` transforms — they betray "stock motion library" tells.
4. **Number count-up.** KPI numbers tween from 0 to their target value
   over 800ms using a custom easing that frontloads the motion (most of
   the value reveals in the first 400ms, the last digit settles in the
   tail). Once per card lifetime, gated on `IntersectionObserver`.
5. **Dismiss animation.** Card slides right (`x: 0 → 120%`) and fades,
   ~`MOTION.d.fast`. Optimistic UI removes from feed immediately; a
   bottom-right toast shows "Dismissed. Undo (5s)". Reverting calls
   `POST /api/insights/{id}/restore` (new endpoint that nulls
   `dismissed_at`).
6. **Command palette.** `cmdk` library, `Cmd/Ctrl+K` to open. Actions:
   regenerate insights, jump to Ask, jump to Dashboard / Accounts /
   Categories / Transactions / Reports, filter feed by card type,
   dismiss all of a given card type. No fuzzy search on transactions in
   this PR — that's a follow-up.

### Card type: Category Drift

**Why.** YNAB shows you what you spent this month. It does not tell you
that Groceries has crept up 33% over the year. Drift is the most useful
forward-looking diagnostic in personal finance that YNAB conspicuously
doesn't surface.

**Detection.** For each on-budget expense category:

- Pull the last 12 months of net spending per month (already aggregated
  via `monthly_trend`).
- Trailing quarter: months `[-3, -1]` inclusive (the three months
  before the current incomplete one — using the in-progress month
  would skew low).
- Prior quarters: months `[-12, -4]` averaged, then compared.
- Drift % = (trailing_q_avg − prior_avg) / prior_avg.
- Drift $ = (trailing_q_avg − prior_avg).
- Flag when `abs(drift%) ≥ 0.15 AND abs(drift$) ≥ $50`.
- Both upward (overspending) AND downward drift surface. Downward
  reads as "$X/mo freed up — reallocate?".

**LLM enhancement** (optional, degradation-safe like the rest): given
the structured payload (category name, drift %, dollar impact,
sparkline points), write one sentence framing the trend. Never invent
numbers; only reuse what's in the payload.

**Card body.** Drift % in hero position (`+33%` in destructive red,
`−12%` in emerald green). Dollar impact below as muted secondary copy.
A 12-point inline SVG sparkline of the monthly nets. Category name as
title.

**Detail view.** Full Tremor LineChart of the 12 monthly nets,
transactions list filtered to this category (sortable by amount and
date), and a "Discuss in Ask" CTA pre-loaded with "What changed about
my {category} spending over the last year?".

**Dedup key:** `drift:{category_id}:{year_month}`. One refreshed
insight per category per month.

**Cadence:** monthly (1st of the month, 03:50 UTC).

### Card type: Year in Money

**Why.** The "Spotify Wrapped" energy — but restrained. A scheduled
retrospective is one of the few moments where the user actively wants
the app to make a story out of their data. Annual + quarterly variants
both ship.

**Trigger cadences.**

- **Annual:** Jan 1, looking back at the prior calendar year. Requires
  ≥ 12 months of synced data.
- **Quarterly:** Apr 1 / Jul 1 / Oct 1, looking back at the prior
  calendar quarter. Requires ≥ 3 months of synced data.

**Generation.** Mostly LLM-driven, deterministic underneath.
Deterministic stats assembled by Python:

- `total_income`, `total_spending`, `net_income`
- `top_categories` (top 3 by net spend, with dollar amounts)
- `top_payees` (top 5 by frequency × amount)
- `savings_rate_trend` (monthly savings rates as a series)
- `biggest_single_transaction` (largest absolute amount, with payee
  and date)
- `largest_category_swing` (category with biggest delta vs prior
  period — Category Drift's logic at year/quarter granularity)

These all feed the LLM prompt that writes the narrative ("a quiet
year for housing, a noisy one for travel" — that voice). Prompt
explicitly says: human voice, restrained, no exclamation points, no
over-praise of habits, no inflated significance.

**Card body.** Compact:

- Title: "Your 2025 in money" or "Q3 2025".
- 3–4 stats: total income, total spending, savings rate, biggest
  single moment (e.g. "Largest single: $4,287 to Pariveda Solutions").
- "Open" affordance leading to the detail view.

**Detail view: full-page route, not modal.** Decision: a modal would
make the scroll math fragile and would hide the URL when the user
inevitably wants to share it. Multi-panel layout, fade-and-slide on
scroll (`MOTION.e.out`):

1. **Hero** — title + total income / total spending side-by-side, big
   tabular numerals, savings rate as a small chip.
2. **Top 3 categories** — horizontal bars, color-coded.
3. **Top payees** — list with amounts, no chart.
4. **Savings rate trend** — Tremor sparkline.
5. **Biggest single moment** — single transaction in a hero card.
6. **The narrative** — LLM-written paragraph(s), serif typeface
   contrast to the surrounding sans, generous line-height.

This view is the screenshot-worthy artifact. Spend judgment here.

**Dedup key:** `year_in_money:{budget_id}:{period_label}` where
`period_label` is `2025` (annual) or `2025-Q3` (quarterly). One
refreshed insight per budget per period.

### Copy voice

Two principles, applied everywhere:

1. **Minimal.** Cut copy that isn't needed. An empty state needs a
   sentence, not a paragraph. A tooltip on an obvious icon usually
   shouldn't exist. Disclaimers and labels often add noise without
   adding information.
2. **Natural.** What stays gets rewritten to sound like a person wrote
   it. No marketing voice, no over-explanation, no fake friendliness,
   no exclamation points, no emoji.

A few before/after pairs to make the bar concrete:

| Before | After |
| --- | --- |
| "Welcome to your YNAB Insights dashboard! Let's get started." | "No insights yet. Generate to see what's worth your attention." |
| "An error occurred while loading the data. Please try again later." | "Couldn't reach YNAB. Retry?" |
| "AI-powered subscription detection identified the following recurring charges." | "11 recurring charges. $147 a month." |

LLM-generated copy (Year in Money narrative, optional card summaries)
gets the same guidance baked into the system prompt rather than
post-processed.

### Out of scope (future PRs)

- Per-user theme customization.
- Animated cover image for Year in Money.
- Social-card meta tags for sharing.
- Mobile-specific motion tuning.
