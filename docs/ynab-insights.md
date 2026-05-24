# YNAB Insights, v2.5 plan

Multi-tenant, zero-persistence refactor. Every architectural choice below exists to make one claim true: **no user data is ever written to disk on the server**. Tokens, YNAB data, and generated insights live in process memory, scoped to a session, evicted on TTL.

This is the precondition for v2.6 (public launch via Cloudflare Tunnel).

## Decisions made up-front

These were left to Claude Code in the scope; capturing them here so they're not re-litigated in PR review.

- **One budget per session.** After token entry, the user picks a budget from their YNAB account. The session stores a snapshot for that one budget. Smaller memory footprint, no `budget_id` query param on every endpoint, and the picker is one tap. Re-pick by ending the session and starting over.
- **`cachetools.TTLCache`, single uvicorn worker.** Redis is overkill for the v2.5 single-host deployment. The cost is that horizontal scaling needs Redis; that's a v2.7+ problem if it ever materializes. Document the constraint, don't pre-build for it.
- **Settings page, not dropdown.** The privacy notice, session expiry, "End session" button, and "Refresh YNAB data" all want room to breathe. A dropdown turns these into hidden affordances.
- **Onboarding: centered card on full-screen aurora.** The brand (logo, aurora, motion) is the user's first impression. Modals feel temporary; bare utility forms feel clinical. A centered card on the live aurora background reads "considered." The card holds the two inputs, validation feedback, the privacy notice, and the "Get a YNAB token" / "Get an Anthropic key" links.

## Session model

```
client                                                      server
------                                                      ------
POST /api/session  <-------------------- token + key
                   ----- validate YNAB, validate Anthropic, fetch budgets -->
                   <-- {budgets: [...], session_id (cookie set)} ------------
POST /api/session/budget  <-- budget_id (from picker)
                   ----- fetch snapshot ---------------------------------->
                   <-- {expires_at, last_synced_at} ------------------------
GET  /api/insights         (cookie -> session lookup -> snapshot)
POST /api/insights/generate
POST /ask          (uses session.anthropic_key)
POST /api/session/refresh  (re-pulls YNAB snapshot)
DELETE /api/session         (evicts, clears cookie)
```

**Cookie:** `sid`. `HttpOnly`, `Secure`, `SameSite=Strict`, `Path=/`, `Max-Age=14400` (4h hard cap). Signed via `itsdangerous` so the server can detect tampering without keeping a server-side index of valid IDs (the session ID itself isn't secret, but signed cookies make 401-handling cheaper: an unsigned/forged cookie is rejected before the cache lookup).

**TTLCache config:**

```python
sessions: TTLCache[str, UserSession] = TTLCache(maxsize=500, ttl=3600)
```

- `maxsize=500` caps concurrent sessions. Cap before the VM (2GB RAM) runs out under estimated 5-10MB per session. When the cap is hit, the LRU eviction is fine (oldest idle session loses).
- `ttl=3600` is the 1h **idle** TTL. The cookie's 4h `Max-Age` is the **absolute** ceiling. Every authenticated request bumps the cache entry's TTL by re-inserting it (`sessions[sid] = sessions[sid]`); the cookie's `Max-Age` is set once at session creation and not refreshed.

**`UserSession` shape:**

```python
class UserSession(BaseModel):
    sid: str                       # uuid4, also the cookie value
    ynab_token: SecretStr          # never serialized to logs / responses
    anthropic_key: SecretStr
    budget_id: str | None          # populated by POST /api/session/budget
    snapshot: YnabSnapshot | None  # populated alongside budget_id
    created_at: datetime
    last_synced_at: datetime | None
    last_active_at: datetime
```

`SecretStr` for tokens so `repr()` / `model_dump()` redact them by default. The serializer used on `GET /api/session` returns only `{created_at, expires_at, last_synced_at, budget_id, budget_name}`. No tokens, no snapshot.

## In-memory data layer (replacing SQLAlchemy)

The generators today take a `(session: AsyncSession, settings, budget_id)` and run SQL queries through `app/services/queries.py`. v2.5 replaces all that with a `YnabSnapshot` Pydantic model and pure-Python aggregations.

```python
class YnabSnapshot(BaseModel):
    budget_id: str
    budget_name: str
    currency_iso: str
    fetched_at: datetime
    accounts: list[Account]
    categories: list[Category]
    payees: list[Payee]
    transactions: list[Transaction]  # sorted by date desc on fetch
```

`Account`, `Category`, `Payee`, `Transaction` are Pydantic versions of the current SQLAlchemy models (same field set, no ORM machinery). The existing `app/schemas/*.py` already define API shapes; v2.5 unifies the internal data model on those.

**Aggregation strategy.** A new `app/snapshot/queries.py` module mirrors the public surface of `app/services/queries.py` (`spending_by_category`, `monthly_trend`, `period_summary`, `category_monthly_history`, etc.) but operates on `YnabSnapshot` in memory. Tests in `test_snapshot_queries.py` assert parity with the SQL versions on fixed fixtures, then we delete the SQL versions.

Why a parallel module instead of editing in-place: the SQL versions stay green through generator refactors; one generator migrates at a time. Once all six are on the snapshot, the SQL module and `app/services/queries.py` get deleted in one commit.

**Why this is fast enough.** A year of transactions for one budget is typically 3-8k rows. The most expensive aggregation (`category_monthly_history` with 12 months × N categories) does ~12 sequential scans of the transactions list filtered by category. Python list comprehensions over ~5k rows complete in single-digit milliseconds. No indexes needed.

## Dismissal pattern (localStorage)

Server is intentionally stateless about dismissals. Two reasons: zero-persistence is the headline product claim, and per-user state would require an account system this product refuses to build.

**Client storage shape:**

```ts
// frontend/lib/dismissals.ts
const KEY = "ynab-insights:dismissed";
type Dismissed = Record<string, number>; // dedup_key -> unix epoch ms
```

The `useInsights` hook reads the dismissal map on mount, filters the feed before render, and writes on dismiss. Restore (the v2.4 optimistic-undo toast) deletes the key.

**Cross-session persistence.** Dismissals survive session expiry as long as the browser keeps localStorage. Clearing site data clears them, which is fine: the product never claimed cross-device dismissals.

**Garbage collection.** On mount, drop entries older than 90 days. Insights that haven't surfaced in 90 days won't surface again (their `dedup_key` is bound to category + ISO week, which has rolled over). Bounded growth without coordinating with the server.

## Rate limits

Per-session limits enforced by middleware. The cookie's `sid` is the bucket key; unauthenticated requests bucket on remote address (the public-facing endpoints, `/api/session` create, also need this).

| Endpoint                            | Bucket   | Limit                       | Why                                                              |
| ----------------------------------- | -------- | --------------------------- | ---------------------------------------------------------------- |
| `POST /api/session`                 | IP       | 5 / hour                    | Token validation is the expensive bit (two upstream calls)       |
| `POST /api/session/budget`          | session  | 10 / hour                   | Snapshot fetch costs YNAB API quota                              |
| `POST /api/session/refresh`         | session  | 10 / hour                   | Same                                                             |
| `POST /api/insights/generate`       | session  | 10 / hour                   | Each generation = up to 6 LLM calls on the user's key            |
| `POST /ask`                         | session  | 20 / hour                   | Higher because Ask is the primary interaction                    |
| Everything else (GET reads, dismiss)| session  | 120 / minute                | Cheap; this is just typo-protection against runaway frontends    |

Numbers stay in `app/config.py` as named constants so adjustments are one-line. Middleware returns `429` with `Retry-After` and a clear `{"error": "rate_limited", "scope": "...", "retry_after_seconds": N}` body so the frontend can surface a specific toast.

**Input length cap on `/ask`:** 1000 chars. Enforced at the FastAPI router level (Pydantic `max_length`), returns `422` with a friendly message.

## Agent loop guardrails

Hard ceilings inside the agent wrapper (`app/agent/loop.py`):

```python
AGENT_MAX_TOOL_CALLS = 20
AGENT_MAX_DURATION_SECONDS = 60
AGENT_INPUT_MAX_CHARS = 1000  # also enforced at the router
```

- **Tool-call cap.** The loop tracks calls per turn. When the next iteration would exceed the cap, the loop stops with `stop_reason='max_tool_calls'` and emits a final `event: done`. The user sees whatever partial answer was produced; the SSE stream closes cleanly.
- **Wall-clock cap.** `asyncio.wait_for(agent_run(), timeout=60)` at the outermost call site. On `TimeoutError`, the loop emits `event: error` with `{"message": "Agent exceeded 60s; try a more specific question."}` and closes.
- **Token-bill cap.** Implicit via the call cap; each turn buys at most one Anthropic call. Worst-case bill per `/ask`: 20 calls × ~2k input + 1k output tokens each ≈ $0.10 at Haiku 4.5 rates. The per-hour rate limit (20 asks) caps a single session at ~$2/hr if a malicious user maxes out.

Surface all three caps in the frontend's empty-state copy so users aren't surprised.

## Validation flow on token entry

`POST /api/session` runs these in order. Stops at the first failure, returns a specific `{"error": code, "message": str}`:

1. **Format checks** (`400`). YNAB token: 64-char hex. Anthropic key: starts with `sk-ant-`. Cheap reject before any network call.
2. **Anthropic ping** (`401`). Send a 1-token `messages.create` with `max_tokens=1`. The cheapest meaningful liveness check; verifies the key and that the account has budget. Failure modes:
   - `authentication_error` -> `error: "invalid_anthropic_key"`.
   - `billing_error` -> `error: "anthropic_billing"`.
   - any other -> `error: "anthropic_unavailable"`.
3. **YNAB budgets fetch** (`401`). `GET https://api.ynab.com/v1/budgets`. Failure modes:
   - `401` -> `error: "invalid_ynab_token"`.
   - `429` -> `error: "ynab_rate_limited"` with `retry_after_seconds` from the response header.
   - any other -> `error: "ynab_unavailable"`.
4. **Create session.** UUID4 `sid`, insert into TTLCache, set the cookie, return the budget list for the picker. Token and key are stored in the session and never echoed.
5. **Budget pick** is a separate request (`POST /api/session/budget`) so the picker can render without blocking on the snapshot fetch. Snapshot fetch happens server-side after the user picks.

**Logging on failure.** Never log the token or key. Log only the failure code and the first 4 chars of the input (for support correlation only). Anthropic/YNAB SDK exceptions sometimes include the headers in `repr`; strip those before logging via a small helper.

## Concrete cut/keep list (mapped to current files)

Cut entirely:

- `app/db.py`, `app/models/`, `app/services/queries.py` (parallel `app/snapshot/queries.py` replaces it), `app/services/sync.py`, `app/services/scheduler.py`, `app/services/cache.py`.
- `app/routers/accounts.py`, `budgets.py`, `categories.py`, `payees.py`, `transactions.py`, `reports.py`, `sync.py`, `metrics.py`. (The reports / accounts / transactions pages were already removed in v2.4 nav consolidation, but the routers stayed.)
- `migrations/`, `alembic.ini`.
- Postgres service in `infra/compose/{dev,stage,prod}/docker-compose.yml`.
- Pydantic settings: `database_url`, `postgres_*`, `ynab_token`, `ynab_budget_id`, `anthropic_api_key`. Settings shrinks dramatically.
- Frontend pages: `/accounts`, `/categories`, `/transactions`, `/dashboard`, `/reports` (already removed in v2.4) plus their `loading.tsx` files. `BUDGET_COOKIE` and `getSelectedBudgetId` from `frontend/lib/api.ts`.

Kept and refactored:

- `app/insights/*`: generators get a `(snapshot: YnabSnapshot, anthropic_key: SecretStr)` signature instead of `(session, settings, budget_id)`.
- `app/agent/loop.py`, `stream.py`: accept per-request key; gain the guardrails.
- `app/services/ynab_client.py`: already accepts a token per-instance; add a `fetch_snapshot(budget_id) -> YnabSnapshot` method.
- `app/insights/llm.py`: accept per-request key; the empty-string normalization stays.
- Frontend cards, details, brand layer (logo, aurora, motion, command palette): unchanged.

Added:

- `app/session/store.py` (TTLCache), `app/session/middleware.py` (cookie -> session, injects `request.state.session`), `app/session/models.py` (`UserSession`).
- `app/snapshot/models.py` (Pydantic data shapes), `app/snapshot/queries.py` (in-memory aggregations).
- `app/routers/session.py` (`POST/DELETE/GET/POST /refresh` and `POST /budget`).
- `app/middleware/rate_limit.py` (per-session token bucket, in-memory).
- Frontend: `app/welcome/page.tsx` (onboarding card), `app/settings/page.tsx`, `lib/dismissals.ts`, `lib/session.ts` (client-side session metadata fetch + 401 redirect helper).

## Non-functional checks (acceptance gates)

- `grep -r "ynab_token\|anthropic_key" app/` returns only test fixtures and the session/loop code that needs them.
- Log inspection on a full token-entry + generate + ask flow: zero token/key fragments in the output.
- `docker compose down && up` and verify the welcome screen comes up empty: no sessions, no insights.
- Six card types still surface against a real budget after the migration.
- CI green; stage deploy succeeds; prod deploy succeeds.

## Commit order (mirrors scope)

1. `feat(session): TTLCache-backed session store + cookie middleware + tests`
2. `feat(session): token validation + POST/DELETE/GET /api/session + refresh`
3. `feat(snapshot): YnabSnapshot Pydantic + ynab_client.fetch_snapshot`
4. `refactor(insights): subscription_audit on YnabSnapshot`
5. `refactor(insights): spending_anomaly on YnabSnapshot`
6. `refactor(insights): cashflow_forecast on YnabSnapshot`
7. `refactor(insights): goal_trajectory on YnabSnapshot`
8. `refactor(insights): category_drift on YnabSnapshot`
9. `refactor(insights): year_in_money on YnabSnapshot`
10. `refactor(api): /api/insights/* + /api/ask use session snapshot`
11. `refactor(agent): per-request Anthropic key + loop guardrails`
12. `feat(middleware): per-session rate limits + input caps`
13. `chore: remove APScheduler, db, models, migrations, postgres compose, env vars`
14. `feat(frontend): onboarding card + token entry + validation flow`
15. `feat(frontend): session expiry handling + localStorage dismissals`
16. `feat(frontend): settings page (refresh, end, expiry)`
17. `copy: privacy-first messaging across onboarding, settings, footer`
18. `docs: rewrite ynab-insights.md + READMEs for v2.5 architecture`

One PR into main when complete.
