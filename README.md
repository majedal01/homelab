# homelab

Infrastructure for a single-node Proxmox homelab: the hosts, the public edge, and the
deploy workflow that application repos call. Applications live in their own repos.

## hosts

| Host | What | Config |
| --- | --- | --- |
| proxmox | Proxmox VE 9 on an i5-12600T, one NVMe, two VMs, nightly vzdump | [hosts/proxmox](hosts/proxmox/) |
| 101-media | Jellyfin and the *arr stack, iGPU passthrough, usenet only | [hosts/media](hosts/media/) |
| oracle-edge | Oracle Free ARM VM running Caddy; public ingress over Tailscale | [hosts/edge](hosts/edge/) |
| 100-finance | Runs [personal-finance](https://github.com/majedal01/personal-finance) stage and prod | [hosts/proxmox/vm](hosts/proxmox/vm/) |

Everything talks over Tailscale. GitHub Actions joins the tailnet with an OAuth client
to deploy. Topology in [docs/network.md](docs/network.md).

## deploys

[`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) is a reusable workflow:
copy a compose file to a VM, pull, restart, smoke check. `media-deploy.yml` calls it for
this repo. Application repos build their own images and call it as
`majedal01/homelab/.github/workflows/deploy.yml@main`. Contract and secrets in
[docs/deployment.md](docs/deployment.md).

Host-level config (systemd units, firewall, Caddy) is pushed by each host's `apply.sh`.
The Proxmox host is managed by hand and `hosts/proxmox` is the record of it.

## layout

```
hosts/<host>/       config for one host, README, apply.sh where the host is scripted
.github/workflows/  deploy.yml (reusable), media-ci.yml, media-deploy.yml
docs/               deployment.md, conventions.md, network.md
```
