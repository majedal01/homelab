# Jellyfin

Self-hosted media server for the homelab, with [Infuse](https://firecore.com/infuse)
(Apple TV / iOS) as the primary player and any [Jellyfin client](https://jellyfin.org/clients)
for everyone else. Goal: a polished library for me plus friends and family, with an
automated request-to-watch pipeline.

**Status:** MVP live on the media VM (Jellyfin + Infuse, Direct Play confirmed). Phase 2
*arr stack (Jellyseerr, Prowlarr + FlareSolverr, Radarr, Sonarr, Bazarr, qBittorrent)
deployed on the unified `/data`; one-time wiring next.

## Archetype

This is an **appliance stack**, not a built service. It runs off-the-shelf images
(`jellyfin/jellyfin`, later the LinuxServer.io \*arr images), has nothing to build, runs
as a **single environment**, and is **deployed by hand** to a dedicated media VM. It does
not use the reusable CI deploy workflow. Real state (config, cache, media) lives on the VM,
never in the repo.

## MVP (Phase 1): one movie, in Infuse, over Tailscale

Prerequisite: a media VM on the Proxmox host (Docker, a `deploy` user, Tailscale, a unified
`/data` disk).

```bash
# On the media VM, in the stack folder (e.g. /home/deploy/stacks/jellyfin):
cp .env.example .env            # set PUID/PGID/TZ for the deploy user (`id`)
mkdir -p /data/media/movies
# Drop one film at /data/media/movies/Movie Name (Year)/Movie Name (Year).mkv
docker compose up -d
```

Then:

1. Open `http://<media-vm-tailnet-ip>:8096`, run the setup wizard, create the admin user.
2. Add a **Movies** library pointing at `/data/media/movies`; let it fetch metadata.
3. Install **Infuse** on the Apple TV / iPhone, add a **Jellyfin** source at the tailnet
   address, sign in, play the movie.

**Done when** the movie plays in Infuse and the Jellyfin dashboard shows **Direct Play**
(not Transcode).

## Roadmap

Phase 2 adds the \*arr automation pipeline; Phase 3 adds public HTTPS and hardware
transcoding. Architecture, the request-to-watch flow, the `/data` layout, the remote-access
model, and the reference stack are in [DESIGN.md](DESIGN.md).
