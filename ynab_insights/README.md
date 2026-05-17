# YNAB Insights

A self-hosted, AI-augmented budgeting dashboard built on top of YNAB. Pulls YNAB data into a local Postgres store, exposes a dashboard for browsing it, and lets you ask natural-language questions backed by a Claude agent that queries the local database.

Single-user, accessed privately over Tailscale. No public exposure.

## Phased build

1. **Foundation** (this phase): SQLAlchemy models for the YNAB entities, Alembic migrations, an async YNAB API client, and a manual `POST /sync` endpoint. Tests against a mocked YNAB API.
2. **Read API and scheduled sync**: `/budgets`, `/accounts`, `/categories`, `/transactions` endpoints with filters; APScheduler runs sync on a 30-minute cadence.
3. **Dashboard UI**: Jinja2 templates served by FastAPI with HTMX for interactivity. Account balances, current-month spend by category, recent transactions, category drill-down.
4. **AI agent**: `POST /ask` runs a Claude tool-use loop. Tools are typed Python functions hitting the local database. Returns the synthesized answer plus the tool-call trace.
5. **Polish and observability**: Charts (Chart.js), structured logging, `/metrics` placeholder, hot-query cache.

## Data model

All primary keys are YNAB IDs (UUID strings) so upserts during sync are clean. Amounts are stored as integer cents (YNAB sends milliunits; the sync divides by 10 on ingest) to avoid float rounding.

| Entity      | Key fields                                                                                  |
| ----------- | ------------------------------------------------------------------------------------------- |
| Budget      | `id`, `name`, `currency`, `last_modified_on`                                                |
| Account     | `id`, `budget_id`, `name`, `type`, `balance`, `on_budget`, `closed`                         |
| Category    | `id`, `budget_id`, `category_group_id`, `name`, `hidden`                                    |
| Payee       | `id`, `budget_id`, `name`, `transfer_account_id`                                            |
| Transaction | `id`, `budget_id`, `account_id`, `category_id`, `payee_id`, `date`, `amount_cents`, `memo`, `cleared`, `approved` |

## Non-functional requirements

- **Idempotent syncs.** Re-running a sync never duplicates data; upsert by YNAB ID.
- **Secrets in env vars.** `YNAB_TOKEN` and `ANTHROPIC_API_KEY` live in per-env `.env` files on the VM, never committed.
- **Rate-limited API calls.** YNAB caps at 200 requests per hour per token. The client tracks remaining requests via response headers and backs off if approaching the ceiling.
- **Strict types.** mypy strict applies. Pydantic models for all external boundaries (YNAB responses, API request/response, AI tool I/O).
- **No app-layer auth.** Tailscale is access control. Single-user product.
- **Privacy hygiene.** Tokens redacted from logs. Only ship transaction data into AI requests when needed.

## Out of scope (deferred)

Multi-user support and login. Public internet exposure (Cloudflare Tunnel is a platform-level future). YNAB write operations. Mobile UI polish. Real-time YNAB webhooks. React or other heavy frontend frameworks. Custom design systems.

## Design decisions for Phase 1

These are tradeoffs called in the foundation PR. Each can be revisited:

- **Direct ORM access in services, no repository pattern.** Fewer layers in v0. Extract repositories later if query logic starts duplicating across services.
- **Upserts via SELECT-then-INSERT-or-UPDATE in Python, not Postgres `ON CONFLICT`.** Portable across SQLite (unit tests) and Postgres (prod). Loses some efficiency. Revisit if sync gets slow.
- **Full sync every time, no delta sync.** YNAB supports `last_knowledge_of_server` for delta sync; that's a Phase 2 optimization once we know real-world data volumes.
- **Foreign keys yes, ORM relationships yes, no cascade delete.** Cascade adds destruction risk; defer until needed.
- **YNAB token optional in Settings.** App boots without it; `POST /sync` returns 503 if it's missing. Lets the app deploy before YNAB is configured.
- **`POST /sync` runs synchronously.** Phase 2 introduces background scheduling. For personal budgets, sync takes seconds.
- **YNAB tests use `respx` to mock httpx.** Purpose-built for httpx, cleaner than VCR.
- **Test DB: SQLite in-memory via `aiosqlite`.** Adequate for Phase 1 (no Postgres-specific types yet). Will migrate to testcontainers-postgres when sync tests need Postgres features.

## Local development

```bash
cd ynab_insights
pip install -e ".[dev]"
pytest
```

To run the service against a real Postgres locally, use the root infra stack:

```bash
cd ../infra
cp .env.example .env
# edit .env
docker compose up
```

The app is at `http://localhost:8000`. Deployment details: [`../docs/deployment.md`](../docs/deployment.md).
