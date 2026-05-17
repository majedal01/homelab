# Deployment

## Branching strategy

Trunk-based. One long-lived branch (`main`); no environment branches.

| Environment | Trigger                                  |
| ----------- | ---------------------------------------- |
| stage       | Auto on every push to `main`             |
| prod        | Manual `workflow_dispatch` against `main` |

Work flows: feature branch -> PR into `main` (CI gates). On merge, stage auto-deploys whatever main now is. Prod waits for a manual trigger; running the `Deploy prod` workflow from the Actions UI deploys whatever main currently is. The manual trigger is the intentional human gate before a prod deploy.

## Hosting

Both stage and prod run on the same Ubuntu VM, reached over Tailscale. They are fully separated as distinct Docker Compose stacks:

| Env   | Stack folder on VM             | App port |
| ----- | ------------------------------ | -------- |
| stage | `/home/deploy/stacks/stage`    | 8001     |
| prod  | `/home/deploy/stacks/prod`     | 8002     |

Each stack has its own `.env` file (managed manually on the VM, never committed) and its own Postgres container with a named volume, so a stage outage cannot touch prod data.

## Deploy flow (stage)

1. GitHub Actions runner checks out the repo.
2. Builds the `ynab_insights` image from its Dockerfile.
3. Pushes the image to `ghcr.io/majedal01/homelab/ynab_insights` with tags `stage-<sha>` and `stage-latest`, authenticated via the workflow's `GITHUB_TOKEN`.
4. Joins the tailnet using the Tailscale GitHub Action with the OAuth credentials, tagged `tag:ci`.
5. `scp` the env-specific compose file to `/home/deploy/stacks/stage/` on the VM.
6. SSH into the VM and run `docker compose pull && docker compose up -d` in that folder. `APP_VERSION` is exported inline as the commit SHA so the running container reports the deployed version.
7. Smoke check: SSH into the VM and `curl http://localhost:8001/health` to confirm the app responds.

## Deploy flow (prod)

Identical to the stage flow above, with these differences:

- Triggered manually via `workflow_dispatch` from the Actions UI, run against `main`.
- Image tags: `prod-<sha>` and `prod-latest`.
- Compose stack at `/home/deploy/stacks/prod` on the VM.
- Smoke check hits `http://localhost:8002/health`.

## Secrets

All set as GitHub Actions repository secrets:

| Secret                | Purpose                                                  |
| --------------------- | -------------------------------------------------------- |
| `SSH_DEPLOY_KEY`      | Private key for the `deploy` user on the VM             |
| `VM_HOSTNAME`         | Tailscale hostname of the VM (e.g. `100-ubuntu`)        |
| `VM_DEPLOY_USER`      | Login user on the VM (`deploy`)                          |
| `TS_OAUTH_CLIENT_ID`  | Tailscale OAuth client ID for the runner to join tailnet |
| `TS_OAUTH_SECRET`     | Tailscale OAuth client secret                            |

`GITHUB_TOKEN` is provided automatically by Actions and is used to authenticate `docker push` against `ghcr.io`.
