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
