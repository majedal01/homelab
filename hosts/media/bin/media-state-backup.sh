#!/usr/bin/env bash
# Stream the media stack's app state as a zstd tar on stdout: Jellyfin users and watch
# history, the *arr databases, Seerr, the compose .env. Everything else under /data or
# in the caches is re-downloadable or regenerated, so it is left out.
#
# Run by the Proxmox host's nightly pull over ssh (see hosts/proxmox). Containers are
# paused for the tar so the SQLite files are not torn; the trap resumes them even if
# tar fails. vzdump cannot do this: it is block-level for QEMU guests and the media disk
# is excluded from it.
set -euo pipefail
stack=/home/deploy/stacks/jellyfin
cd "$stack"
docker compose pause >&2
trap 'docker compose unpause >&2' EXIT
tar -C "$stack" \
  --exclude=./cache --exclude=./config/cache --exclude=./config/log \
  --exclude=./config/transcodes --exclude=./recyclarr/resources --exclude=./recyclarr/logs \
  --exclude='./*/logs' --exclude='./*/log' --exclude='./*/MediaCover' --exclude='./*/Backups' \
  --warning=no-file-changed -cf - . | zstd -3 -T0 -q
