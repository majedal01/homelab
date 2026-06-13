# Conventions

How apps are named and namespaced in this monorepo so adding the Nth app never
collides with the others. One source of truth; update this when a new app lands.

## App taxonomy

- Every app lives at `apps/<domain>/<app>/` and is self-contained: code, deploy
  manifests (`deploy/`), and docs (`README.md`, `DESIGN.md`) live together.
- The `<domain>` folder groups related apps and holds no code of its own
  (`apps/finance/` is the finance domain; `apps/finance/ynabInsights/` is the app).
- Adding an app to an existing domain is a new sibling folder; a brand-new domain is a
  new top-level folder under `apps/`.

## Naming

App names are **camelCase**, no `_` or `-` (e.g. `ynabInsights`, `jellyfin`). The
**domain lives only in the repo path**. Operational identifiers below use the
**lowercased app leaf** (OCI image refs and DNS are lowercase-only), so `ynabInsights`
becomes `ynabinsights` for images, the VM stack folder, and workflow file names.

## Archetypes

- **Built service** - custom code compiled into an image, pushed to ghcr, pulled on
  deploy (e.g. `ynabInsights`). Uses the reusable deploy workflow.
- **Appliance stack** - off-the-shelf images wired by compose, nothing to build
  (e.g. the media stack). Deployed by hand; does not use the reusable workflow.

## Namespacing table

| Concern          | Pattern                                                       | ynabInsights                                         |
| ---------------- | ------------------------------------------------------------ | ---------------------------------------------------- |
| App folder       | `apps/<domain>/<app>/`                                        | `apps/finance/ynabInsights/`                         |
| Deploy manifest  | `apps/<domain>/<app>/deploy/<env>/docker-compose.yml`        | `apps/finance/ynabInsights/deploy/{dev,stage,prod}/` |
| Image (backend)  | `ghcr.io/majedal01/homelab/<app-lower>:<env>-<sha\|latest>`   | `.../ynabinsights:stage-latest`                      |
| Image (frontend) | `ghcr.io/majedal01/homelab/<app-lower>_frontend:<env>-<...>`  | `.../ynabinsights_frontend:stage-latest`             |
| VM stack folder  | `/home/deploy/stacks/<app-lower>/<env>`                      | `/home/deploy/stacks/ynabinsights/{stage,prod}`      |
| Compose project  | top-level `name: <app-lower>-<env>` in each compose          | `ynabinsights-stage`, `ynabinsights-prod`            |
| Host port        | registered pair per app (see registry)                       | stage 8001, prod 8002                                |
| Subdomain        | `<name>.majed.fyi`                                           | `ynab.majed.fyi`                                     |

Set the Compose project name explicitly with `name:` in every compose file. Without it,
Docker Compose derives the project from the stack-directory basename, so two apps' `stage`
folders would both become project `stage` and clobber each other.

## Port registry

| App          | Stage | Prod | Notes                                       |
| ------------ | ----- | ---- | ------------------------------------------- |
| ynabInsights | 8001  | 8002 | FastAPI internal-only; Next.js on host port |
| media/jellyfin | -   | 8096 | Jellyfin; single env (appliance)            |

## CI/CD

- Per-app workflows: `.github/workflows/<app-lower>-ci.yml` (+ `-frontend-ci.yml`),
  path-filtered to `apps/<domain>/<app>/**`.
- Built services deploy via the reusable `.github/workflows/deploy.yml`
  (`workflow_call`), called by `<app-lower>-deploy-<env>.yml` with:
  - `app` - lowercased app leaf; image repo base and VM stack folder (e.g. `ynabinsights`).
  - `app_dir` - repo path under `apps/`; build context and compose source (e.g. `finance/ynabInsights`).
  - `environment`, `port`.

  GitHub requires reusable workflows to live in `.github/workflows/`.
