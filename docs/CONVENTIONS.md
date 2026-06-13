# Conventions

How apps are named and namespaced in this monorepo so adding the Nth app never
collides with the others. One source of truth; update this when a new app lands.

## App taxonomy

- Each app is a folder under `apps/`, self-contained: code, deploy manifests
  (`apps/<app>/deploy/`), and docs (`README.md`, `DESIGN.md`) live together.
- Domains are flat: `apps/finance` and `apps/media` are siblings. When a domain
  grows a second app, nest to `apps/<domain>/<app>/` at that point, not before.

## Naming

App names are **camelCase**, no `_` or `-` (e.g. `finance`, `media`, `mediaServer`).
The derived identifiers below are lowercased where the spec requires it (OCI image
refs and DNS are lowercase-only), so single-word names are unchanged and only
multi-word names differ in those spots.

## Archetypes

- **Built service** - custom code compiled into an image, pushed to ghcr, pulled on
  deploy (e.g. `finance`). Uses the reusable deploy workflow.
- **Appliance stack** - off-the-shelf images wired by compose, nothing to build
  (e.g. `media`). Deployed by hand; does not use the reusable workflow.

## Namespacing table

| Concern          | Pattern                                                        | finance                                    |
| ---------------- | -------------------------------------------------------------- | ------------------------------------------ |
| App folder       | `apps/<app>/`                                                  | `apps/finance/`                            |
| Deploy manifest  | `apps/<app>/deploy/<env>/docker-compose.yml`                   | `apps/finance/deploy/{dev,stage,prod}/`    |
| Image (backend)  | `ghcr.io/majedal01/homelab/<app>:<env>-<sha\|latest>`          | `.../finance:stage-latest`                 |
| Image (frontend) | `ghcr.io/majedal01/homelab/<app>_frontend:<env>-<sha\|latest>` | `.../finance_frontend:stage-latest`        |
| VM stack folder  | `/home/deploy/stacks/<app>/<env>`                              | `/home/deploy/stacks/finance/{stage,prod}` |
| Host port        | registered pair per app (see registry)                         | stage 8001, prod 8002                      |
| Subdomain        | `<app>.majed.fyi`                                              | `ynab.majed.fyi` (legacy; may move)        |

## Port registry

| App     | Stage | Prod | Notes                                       |
| ------- | ----- | ---- | ------------------------------------------- |
| finance | 8001  | 8002 | FastAPI internal-only; Next.js on host port |
| media   | -     | 8096 | Jellyfin; single env (appliance)            |

## CI/CD

- Per-app workflows: `.github/workflows/<app>-ci.yml` (+ `-frontend-ci.yml`),
  path-filtered to `apps/<app>/**`.
- Built services deploy via the reusable `.github/workflows/deploy.yml`
  (`workflow_call`), called by `<app>-deploy-<env>.yml` with `app`, `environment`,
  and `port`. GitHub requires reusable workflows to live in `.github/workflows/`.
