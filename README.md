# homelab

A personal homelab platform for practicing enterprise software engineering patterns end to end on owned hardware.

## Architecture

```mermaid
graph TD
    Dev[Developer] -->|git push| GH[GitHub]
    GH -->|push to main| GHA1[Deploy stage workflow]
    GH -->|manual trigger on main| GHA2[Deploy prod workflow]
    GHA1 -->|build and push| GHCR[ghcr.io]
    GHA2 -->|build and push| GHCR
    GHA1 -->|OAuth + SSH| TS[Tailscale tailnet]
    GHA2 -->|OAuth + SSH| TS
    TS --> VM[Ubuntu VM]
    GHCR -.->|docker compose pull| VM
    VM --> Stage[Stage stack :8001]
    VM --> Prod[Prod stack :8002]

    Proxmox[Proxmox VE] -.->|hosts| VM
    Router[GL.iNet Beryl AX] -.->|provides network| Proxmox
```

## Tech stack

| Layer          | Tools                                                          |
| -------------- | -------------------------------------------------------------- |
| Infrastructure | Proxmox VE, GL.iNet Beryl AX, Tailscale                        |
| Compute        | Ubuntu 25.04 VM, Docker, Docker Compose                        |
| Backend        | Python 3.12, FastAPI 0.110+, Pydantic 2+, PostgreSQL 16        |
| Frontend       | Next.js 15 (App Router), TypeScript strict, Tailwind, shadcn/ui |
| Tooling        | Ruff 0.4+, mypy 1.10+ (strict), pytest 8+, hatchling, ESLint   |
| CI/CD          | GitHub Actions, GitHub Container Registry                      |

## Pipeline

1. Feature branch off `main`, push, open a PR. [CI](.github/workflows/ci.yml) runs Ruff, mypy strict, and pytest on every PR.
2. Merge into `main`. [Stage deploy](.github/workflows/deploy-stage.yml) fires automatically: build, push to ghcr.io, scp + ssh deploy over Tailscale, smoke-check `/health` on :8001. Stage is always whatever main is.
3. Promote to prod via manual [prod deploy](.github/workflows/deploy-prod.yml) from the Actions UI. Same flow, deploys to :8002. The manual step is the intentional human gate before prod.

Full design in [`docs/deployment.md`](docs/deployment.md).

## Hosted applications

### YNAB Insights

**Status:** Live. **URL:** [ynab.majed.fyi](https://ynab.majed.fyi)

An AI financial coach that lives alongside YNAB. Try the demo without signing up. Bring your own Anthropic or OpenAI key to use your real YNAB data. Zero persistence: keys and data never touch disk.

The app surfaces a feed of forward-looking cards (subscriptions, spending anomalies, cashflow forecasts, category projections, debt payoff, goal trajectories, category drift, year/quarter retrospectives). An agent (`Ask`) answers natural-language follow-ups via your provider's tool-use API. FastAPI + Next.js.

- Source: [`ynab_insights/`](ynab_insights/) (backend + frontend live together)
- Design notes: [`ynab_insights/DESIGN.md`](ynab_insights/DESIGN.md)
- Screenshots: [`ynab_insights/screenshots/`](ynab_insights/screenshots/) *(placeholder — to be populated)*

## Skills demonstrated

- Strict CI pipeline (Ruff lint and format, mypy strict, pytest) gating every PR. See [`ci.yml`](.github/workflows/ci.yml).
- Two-environment CD: stage deploys automatically on merge, prod deploys via manual `workflow_dispatch` as an intentional gate. Both build versioned Docker images, push to ghcr.io, and roll the running container over SSH with a `/health` smoke check. See [`deploy-stage.yml`](.github/workflows/deploy-stage.yml) and [`deploy-prod.yml`](.github/workflows/deploy-prod.yml).
- Zero-trust remote access: ephemeral CI runners join a Tailscale mesh with tag-based ACLs, so the VM never needs a public IP.
- Stage and prod separated into isolated Compose stacks on the same host. Own Postgres volume, own host port. A stage outage can't reach prod data.

## Platform roadmap

- Cloudflare Tunnel to expose select services on public URLs without opening firewall ports.
- Observability: Prometheus for metrics, Grafana for dashboards, Loki for log aggregation.
- Infrastructure as code: Terraform or OpenTofu to declare the VM, Tailscale ACLs, and Cloudflare resources.

Application-specific roadmaps live in each app's own folder.

## Repo structure

Monorepo. Platform-wide concerns (infra, CD, cross-cutting docs) live at the root; everything specific to a hosted app lives inside that app's folder.

- [`ynab_insights/`](ynab_insights/): YNAB Insights app. FastAPI backend ([`ynab_insights/app/`](ynab_insights/app/)), Next.js frontend ([`ynab_insights/frontend/`](ynab_insights/frontend/)), tests, Dockerfiles, app-specific design notes ([`DESIGN.md`](ynab_insights/DESIGN.md)).
- [`infra/compose/`](infra/compose/): per-environment Docker Compose stacks (`dev`, `stage`, `prod`). Platform-level: knows how to assemble app containers into a deployable stack.
- [`docs/`](docs/): platform docs ([`deployment.md`](docs/deployment.md)). App-specific design notes live in their app folder.
- [`.github/workflows/`](.github/workflows/): CI and CD pipelines.

## Local development

```bash
git clone git@github.com:majedal01/homelab.git
cd homelab
cp infra/compose/dev/.env.example infra/compose/dev/.env
# Fill in optional YNAB_TOKEN, ANTHROPIC_API_KEY if you want sync/ask working.
docker compose -f infra/compose/dev/docker-compose.yml up
```

Frontend at `http://localhost:3000`, FastAPI at `http://localhost:8000`. Both hot-reload on source changes. Deployment details in [`docs/deployment.md`](docs/deployment.md).

## Built with AI assistance

Code in this repo was written with Claude (Anthropic) as a paired collaborator. The architecture, design decisions, and review of every change were mine; Claude accelerated boilerplate, surfaced edge cases, and drafted prose I could prune. Treating AI as a high-bandwidth pair, with the same review bar as any other contributor, is itself a skill this project is meant to demonstrate.
