# Jellyfin

Self-hosted media server for the homelab, with [Infuse](https://firecore.com/infuse)
(Apple TV / iOS) as the primary player and any [Jellyfin client](https://jellyfin.org/clients)
for everyone else. Goal: a polished library for me plus friends and family, with an
automated request-to-watch pipeline.

**Status:** scaffolding the MVP (Phase 1). Not yet deployed.

## Archetype

This is an **appliance stack**, not a built service. It runs off-the-shelf images
(`jellyfin/jellyfin`, later the LinuxServer.io \*arr images), has nothing to build, runs
as a **single environment**, and is **deployed by hand** to a dedicated media VM. It does
not use the reusable CI deploy workflow. Real state (config, cache, media) lives on the VM,
never in the repo.

## MVP (Phase 1): one movie, in Infuse, over Tailscale

Prerequisite: a media VM on the Proxmox host, on the tailnet, with Docker, a `deploy`
user, and a unified `/data` disk (see [DESIGN.md](DESIGN.md)).

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

- **Phase 2** - the \*arr automation pipeline (Seerr, Radarr/Sonarr, Prowlarr +
  FlareSolverr, qBittorrent, Bazarr) on the TRaSH single-`/data` hardlink layout.
- **Phase 3** - public HTTPS for non-Apple/non-technical family (Caddy + `jellyfin.majed.fyi`),
  Intel QuickSync hardware transcoding, and Jellyfin user management.

Full architecture, the request-to-watch flow, the `/data` layout, remote-access model, and
the worked reference stack are in [DESIGN.md](DESIGN.md).
