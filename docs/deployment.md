# deployment

Trunk-based. One long-lived branch, `main`. Feature branch, PR, CI, merge. Merge
deploys stage; prod is a manual run of the same workflow against `main`.

## the reusable workflow

`.github/workflows/deploy.yml` does one thing: put a compose file on a VM and bring the
stack up. It joins the tailnet, copies the file to `/home/deploy/stacks/<stack>/`,
optionally writes env lines and logs in to ghcr.io, runs `docker compose pull && up -d
--remove-orphans`, curls a health URL, and prunes dangling images. It builds nothing.

| Input | Meaning |
| --- | --- |
| `stack` | Folder under `/home/deploy/stacks`, e.g. `jellyfin` or `ynabinsights/stage` |
| `compose_file` | Path in the caller's checkout |
| `health_url` | Curled on the VM after `up`, with retries |
| `version` | Exported as `APP_VERSION`; defaults to the commit SHA |

| Secret | Meaning |
| --- | --- |
| `ssh_key` | Private key for the `deploy` user on the VM |
| `vm_hostname` | Tailnet name of the VM |
| `vm_user` | `deploy` |
| `ts_oauth_client_id`, `ts_oauth_secret` | Tailscale OAuth client tagged `tag:ci` |
| `registry_token` | Optional. `GITHUB_TOKEN` if the images are private |
| `env_lines` | Optional. `KEY=VALUE` lines upserted into the stack's `.env` |

Secrets are passed explicitly, never inherited, so one caller can target the media VM
and another the finance VM with the same workflow.

## calling it from an application repo

Build and push images in a job of your own, then:

```yaml
deploy:
  needs: build
  uses: majedal01/homelab/.github/workflows/deploy.yml@main
  with:
    stack: myapp/stage
    compose_file: deploy/stage/docker-compose.yml
    health_url: http://localhost:8001/health
  secrets:
    ssh_key: ${{ secrets.SSH_DEPLOY_KEY }}
    vm_hostname: ${{ secrets.VM_HOSTNAME }}
    vm_user: ${{ secrets.VM_DEPLOY_USER }}
    ts_oauth_client_id: ${{ secrets.TS_OAUTH_CLIENT_ID }}
    ts_oauth_secret: ${{ secrets.TS_OAUTH_SECRET }}
    registry_token: ${{ secrets.GITHUB_TOKEN }}
```

The calling repo needs `SSH_DEPLOY_KEY`, `VM_HOSTNAME`, `VM_DEPLOY_USER`,
`TS_OAUTH_CLIENT_ID` and `TS_OAUTH_SECRET` as Actions secrets. This is a personal
account, so they are set per repo. The stack's `.env` on the VM holds app secrets and is
managed by hand; anything CI must rotate goes through `env_lines`.

## what is not automated

Host-level config under `hosts/<host>/` is pushed with that host's `apply.sh` from a
workstation on the tailnet. The Proxmox host is configured by hand; `hosts/proxmox` is
the record. personal-finance is the worked example of an application repo.
