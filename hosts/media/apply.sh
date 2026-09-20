#!/usr/bin/env bash
# Push host-level units, scripts and recyclarr config to the media VM.
# The compose stack itself deploys through .github/workflows/media-deploy.yml.
set -euo pipefail
host="${1:-root@100.84.50.127}"
stack=/home/deploy/stacks/jellyfin
cd "$(dirname "$0")"
scp -q systemd/* "$host:/etc/systemd/system/"
scp -q bin/* "$host:/usr/local/sbin/"
scp -q modules-load.d/i915.conf "$host:/etc/modules-load.d/"
# configs is replaced wholesale so a renamed file does not leave a stale copy behind.
ssh "$host" "rm -rf $stack/recyclarr/configs"
scp -qr recyclarr/configs recyclarr/settings.yml "$host:$stack/recyclarr/"
ssh "$host" "chmod 755 /usr/local/sbin/*.sh &&
  chown -R deploy:deploy $stack/recyclarr &&
  systemctl daemon-reload && systemctl enable --now ensure-i915.service jellyfin-cache-guard.timer"
