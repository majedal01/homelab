# media

VM 101, Ubuntu Server, 4 cores, 6G, 300G disk. Tailnet `101-media`. Jellyfin plus the
*arr stack as one compose project at `/home/deploy/stacks/jellyfin`, usenet only.
Library under `/data` (TRaSH single root). Public access via the edge host.

- `docker-compose.yml` deploys through `.github/workflows/media-deploy.yml` (manual run).
  `.env` on the VM holds PUID, PGID, TZ and RENDER_GID.
- `systemd/`, `bin/`, `modules-load.d/` are host-level units, pushed with `apply.sh`:
  - `ensure-i915` loads the i915 module before docker and reinstalls
    `linux-modules-extra` if a kernel upgrade dropped it. Without it the render node
    is missing and QuickSync silently falls back to software.
  - `jellyfin-cache-guard.timer` runs every 20 min: warns at 85% disk, clears the
    transcode cache and prunes images under 20G free, and removes usenet incompletes
    older than two days that SABnzbd is not working on.
- `recyclarr/` syncs TRaSH quality profiles into Radarr and Sonarr. API keys come from
  `recyclarr/secrets.yml` on the VM (see `secrets.yml.example`). Run it ad hoc:
  `docker run --rm -v /home/deploy/stacks/jellyfin/recyclarr:/config ghcr.io/recyclarr/recyclarr sync`.

## disk

The disk has filled twice, once from the transcode cache and once from abandoned usenet
downloads. Symptoms look like Jellyfin auth or network failures because it cannot write
its SQLite database. Check `df -h /` first. Guards beyond the timer: SABnzbd free-space
floor 25G, Radarr and Sonarr minimum free space 25G, and no remux or BR-DISK quality
allowed in any profile.
