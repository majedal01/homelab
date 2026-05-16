# Homelab Project — Working Notes for Claude

## Project context
Personal homelab focused on practicing enterprise software engineering patterns: CI/CD, IaC, stage/prod environments. Mimics FAANG-style stack and tooling.

## Repo structure
- `app/` — FastAPI web application
- `infra/` — Docker Compose files, deployment configs
- `docs/` — architecture notes and decision records

## Stack
- Python 3.12+, FastAPI, Pydantic
- PostgreSQL with SQLAlchemy + Alembic
- pytest + httpx for tests
- Ruff for lint/format, mypy for type checking
- Docker + Docker Compose
- GitHub Actions for CI/CD, ghcr.io for images

## Deployment patterns
- Branch-to-env mapping: `stage` branch deploys to stage, `main` deploys to prod (prod workflow pending).
- Both envs run as separate Docker Compose stacks on the same Tailscale-accessible VM, in `/home/deploy/stacks/{stage,prod}`. Stage uses host port 8001, prod uses 8002.
- Stage deploy (`.github/workflows/deploy-stage.yml`) builds and pushes `ghcr.io/majedal01/homelab/ynab_insights:stage-{sha,latest}`, joins the tailnet via Tailscale OAuth, scps the compose file to the VM, and runs `docker compose pull && up -d` over SSH. A `curl /health` smoke check confirms the deploy.
- Per-env compose files live under `infra/compose/{stage,prod}/`. Each env has its own `.env` on the VM (never committed) with Postgres credentials. The workflow injects `APP_VERSION=<commit sha>` per deploy.
- GitHub Actions secrets used: `SSH_DEPLOY_KEY`, `VM_HOSTNAME`, `VM_DEPLOY_USER`, `TS_OAUTH_CLIENT_ID`, `TS_OAUTH_SECRET`. `GITHUB_TOKEN` (automatic) authenticates ghcr.io pushes.
- Full details in `docs/deployment.md`.

## Workflow rules
- Always work on a feature branch off `main`. Never commit directly to `main`.
- Keep commits small and atomic — one logical change per commit.
- Commit messages: short, imperative ("add health endpoint", "set up postgres compose"). No emoji, no attribution lines, no trailers.
- Show the proposed plan and commit sequence before executing — wait for confirmation.

## Code style
- Idiomatic, type-hinted Python. Clean naming, reasonable function size.
- Comments explain *why*, not *what*. Skip them when the code is self-evident.
- No premature abstraction. Build for what's needed, not what might be.
- No emoji in code, comments, or commits.

## Current state
Empty repo with `app/`, `infra/`, `docs/` folders, each with a README stub.

## Next task
Scaffold the hello-world FastAPI service in `app/`:
- `GET /` returns `{"message": "Hello", "version": "0.1.0", "env": "stage" | "prod"}`
- `GET /health` returns `{"status": "ok"}`
- `env` and `version` come from environment variables so deploys are observable
- Add `Dockerfile`, dependency file (`pyproject.toml` preferred), and pytest smoke tests
- Add `infra/docker-compose.yml` to run the app + Postgres locally