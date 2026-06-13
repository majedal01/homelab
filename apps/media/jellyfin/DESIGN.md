# Jellyfin media stack - design

## Why this shape

A polished, self-hosted media platform for me plus friends and family: Jellyfin as the
server, Infuse as the primary player, with remote access, optional transcoding, user
management, and an automated request-to-watch pipeline. Rolled out MVP-first so the whole
shape is proven on one movie before automation is added.

Two facts drive the design:

1. It is an **appliance**: off-the-shelf images wired by compose, nothing to build, so the
   platform's "build image -> push -> pull" CI model does not apply. It is deployed by hand
   and all state lives on the VM.
2. It runs on its **own media VM** (Proxmox host: Lenovo ThinkCentre M90q, i5-12600T, UHD
   770 iGPU), separate from the app VM that hosts ynabInsights.

## Clients and transcoding

Infuse decodes on the device, so for Infuse clients Jellyfin almost always **Direct Plays**
and does not transcode. The MVP therefore needs no transcoding hardware. Non-Apple viewers
use any Jellyfin client (web, Android/Android TV, Findroid, Roku, Swiftfin); web browsers
and Chromecast are the ones likely to trigger server-side transcoding, which is what the
i5-12600T **QuickSync** iGPU covers in Phase 3 (pass `/dev/dri` into the VM, enable QSV).

## Remote access (hybrid)

- **Now:** Tailscale. Jellyfin binds the VM's tailnet interface; Infuse and other clients
  connect over the tailnet. Zero public exposure.
- **Later (Phase 3):** Caddy reverse-proxy at `jellyfin.majed.fyi` with a Let's Encrypt cert
  via the Cloudflare DNS-01 challenge and a DNS-only (grey-cloud) record, so traffic flows
  directly to the house, bypassing Cloudflare's CDN (which is why the existing Cloudflare
  Tunnel cannot serve media). Only Jellyfin (and optionally Seerr) is ever exposed; the
  \*arr apps stay tailnet-only.

## The *arr pipeline (Phase 2)

Each tool owns one job and they chain:

Seerr (request UI) -> Radarr/Sonarr (movies/TV brains) -> Prowlarr (indexer manager) +
FlareSolverr (Cloudflare-protected indexers) -> qBittorrent (download) -> Bazarr (subtitles)
-> Jellyfin (library).

Request-to-watch: a Seerr request goes to Radarr/Sonarr, which search via Prowlarr, hand the
release to qBittorrent, then hardlink-import and rename into `/data/media`; Jellyfin detects
the file and it appears in every client.

### Unified /data layout (TRaSH)

Downloads and the library must live on **one filesystem** so imports are hardlinks (instant,
no extra disk, torrent keeps seeding) and atomic moves (no slow copy). All containers mount
the single `/data` root, never sub-paths:

```
/data
  torrents/{movies,tv}        # qBittorrent saves here, by category
  usenet/{incomplete,complete}
  media/{movies,tv}           # Jellyfin libraries point here
```

Storage note: the M90q's 512 GB NVMe is shared by Proxmox + both VMs, so plan external
storage (USB SSD/HDD passthrough or a NAS mount, kept on one filesystem) before the pipeline
generates real volume.

## Reference

`standleypg/Jellyfin-Automated-Media-Stack`
(https://github.com/standleypg/Jellyfin-Automated-Media-Stack) is a worked example of this
exact pipeline with a step-by-step one-time-config guide. Adapt to the TRaSH single-`/data`
layout above (it uses separate `/downloads` + `/media`). A VPN sidecar (gluetun) on the
download client is worth adding for public torrent indexers.

## Phases

1. **MVP** - Jellyfin only; one movie; Infuse over Tailscale; confirm Direct Play. (this scaffold)
2. **Automation** - add Seerr, Radarr/Sonarr, Prowlarr + FlareSolverr, qBittorrent, Bazarr
   on the `/data` layout; verify a request lands in the library automatically.
3. **Polish** - Caddy HTTPS + hardening, QuickSync transcoding, Jellyfin user management.
