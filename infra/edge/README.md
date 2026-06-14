# Edge (public ingress)

Caddy on a public-IP VM that fronts the homelab services the internet needs to reach. The
home network is behind double NAT (Xfinity, no usable port-forward), so a box with its own
public IP is the only way to expose anything. It reverse-proxies over Tailscale, so home
services never open a port publicly.

## What runs it

An Oracle Cloud Always Free VM (ARM Ubuntu 24.04), on the tailnet as `oracle-edge`. Caddy
(apt) terminates TLS with Let's Encrypt via the HTTP-01 challenge and proxies each host to
its backend's tailnet address. fail2ban guards SSH. Only `jellyfin` and `jellyseerr` are
exposed; the *arr apps stay tailnet-only.

Hand-managed appliance, not deployed by CI. [Caddyfile](Caddyfile) is the source of truth:
copy it to `/etc/caddy/Caddyfile` on the edge and `systemctl reload caddy`.

## Add an app

1. Point a DNS A record at the edge IP, grey-cloud (DNS-only) so traffic goes straight to
   the edge, not through Cloudflare's CDN.
2. Add a block: `host { reverse_proxy <tailnet-ip>:<port> }`.
3. Reload Caddy; the cert issues automatically.

## Setup notes

- Open 80 and 443 in both the OS firewall (iptables, persisted) and the OCI security list.
- Reserve the public IP so it survives a stop/start; an ephemeral one changes.
- Disable Tailscale key expiry for the edge node, or it deauths and the proxy goes dark.
