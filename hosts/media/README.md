# media

VM 101, Ubuntu Server, 4 cores, 6G, 300G disk. Tailnet `101-media`. Jellyfin plus the
*arr stack as one compose project at `/home/deploy/stacks/jellyfin`, usenet only.
Library under `/data` (TRaSH single root). Public access via the edge host.

- `docker-compose.yml` deploys through `.github/workflows/media-deploy.yml` (manual run).
  `.env` on the VM holds PUID, PGID, TZ, RENDER_GID and the Radarr and Sonarr API keys.
- `systemd/`, `bin/`, `modules-load.d/` are host-level units, pushed with `apply.sh`:
  - `ensure-i915` loads the i915 module before docker and reinstalls
    `linux-modules-extra` if a kernel upgrade dropped it. Without it the render node
    is missing and QuickSync silently falls back to software.
  - `jellyfin-cache-guard.timer` runs every 20 min: warns at 85% disk, clears the
    transcode cache and prunes images under 20G free, and removes usenet incompletes
    older than two days that SABnzbd is not working on.
- `recyclarr/` syncs TRaSH custom formats and the quality profile into Radarr and Sonarr.
  It runs as a compose service on a nightly cron; `apply.sh` pushes the config and `.env`
  holds the API keys. One-off: `docker compose run --rm recyclarr sync`.

## disk

The disk has filled twice, once from the transcode cache and once from abandoned usenet
downloads. Symptoms look like Jellyfin auth or network failures because it cannot write
its SQLite database. Check `df -h /` first. Guards beyond the timer: SABnzbd free-space
floor 25G, Radarr and Sonarr minimum free space 25G, and no remux or BR-DISK quality
allowed in any profile.

## quality

One Radarr profile, `UHD WEB + HD`, for every movie: WEB 2160p on top, then Bluray-1080p
and WEB 1080p, nothing below. A request grabs the best of those that exists, so an older
title lands at 1080p instead of sitting in "missing", and a new one with only 1080p on day
one is upgraded when the 2160p WEB appears (cutoff WEB 2160p, format score up to 10000).
Remux and Bluray-2160p are left out; a 50G remux does not fit this disk. Recyclarr owns
the profile and the format scores.

Size caps are Radarr quality definitions set by hand, in MB per minute, because a
Recyclarr quality_definition sync would overwrite them:

| quality | preferred | max |
|---|---|---|
| WEB 2160p | 120 | 230 |
| Bluray-1080p | 70 | 130 |
| WEB 1080p | 45 | 90 |

Seerr gives new users request plus auto-approve. Email notifications go out through Gmail
SMTP; the app password is entered in the Seerr UI, never stored in the repo.
