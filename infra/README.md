# infra

Per-environment Docker Compose stacks.

| Folder           | Use                                                       |
| ---------------- | --------------------------------------------------------- |
| `compose/dev/`   | Local dev: bind-mounted source, hot reload, no ghcr pulls |
| `compose/stage/` | Stage stack deployed to the VM at port 8001               |
| `compose/prod/`  | Prod stack deployed to the VM at port 8002                |

Each folder owns its `docker-compose.yml` and `.env.example`. On the VM, the
real `.env` lives next to the compose file and is never committed.

See [`../docs/deployment.md`](../docs/deployment.md) for the CD flow.
