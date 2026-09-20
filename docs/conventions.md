# conventions

Naming that keeps hosts and stacks from colliding. Update this when something new lands.

- Hosts live at `hosts/<host>/`, one directory per machine, named by role: `proxmox`,
  `media`, `edge`. A host directory holds its config, a README, and an `apply.sh` if the
  host is scripted.
- Application repos are named for the product (`personal-finance`) and own their code,
  Dockerfiles, compose files and CI. They call this repo's deploy workflow.
- A stack on a VM lives at `/home/deploy/stacks/<stack>[/<env>]`. Set the compose project
  name explicitly with `name: <stack>-<env>` so two stacks' `stage` folders do not
  become the same project.
- Images: `ghcr.io/majedal01/<repo>/<image>:<env>-<sha>` plus `<env>-latest`.
- Subdomains: `<name>.majed.fyi`.

## ports

| Stack | Host | Port |
| --- | --- | --- |
| ynabinsights stage | 100-finance | 8001 |
| ynabinsights prod | 100-finance | 8002 |
| jellyfin | 101-media | 8096 |
| jellyseerr | 101-media | 5055 |
| sabnzbd | 101-media | 8085 |

Commit and PR rules are in `.claude/CLAUDE.md`.
