#!/usr/bin/env bash
# Push host-level units, scripts and recyclarr config to the media VM.
# The compose stack itself deploys through .github/workflows/media-deploy.yml.
set -euo pipefail
host="${1:-root@100.84.50.127}"
cd "$(dirname "$0")"
scp -q systemd/* "$host:/etc/systemd/system/"
scp -q bin/* "$host:/usr/local/sbin/"
scp -q modules-load.d/i915.conf "$host:/etc/modules-load.d/"
scp -qr recyclarr/configs recyclarr/settings.yml "$host:/home/deploy/stacks/jellyfin/recyclarr/"
ssh "$host" 'chmod 755 /usr/local/sbin/ensure-i915.sh /usr/local/sbin/jellyfin-cache-guard.sh &&
  chown -R deploy:deploy /home/deploy/stacks/jellyfin/recyclarr &&
  systemctl daemon-reload && systemctl enable --now ensure-i915.service jellyfin-cache-guard.timer'
