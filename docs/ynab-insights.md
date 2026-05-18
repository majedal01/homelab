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

A new `.github/workflows/frontend-ci.yml` runs on changes to `frontend/**`.
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
