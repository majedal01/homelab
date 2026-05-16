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