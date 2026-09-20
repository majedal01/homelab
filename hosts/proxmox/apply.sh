#!/usr/bin/env bash
# Push the media app-state pull job to the Proxmox host. Everything else in this
# directory is a record of hand-applied config, not an apply target.
set -euo pipefail
host="${1:-root@100.66.36.86}"
cd "$(dirname "$0")"
scp -q bin/* "$host:/usr/local/sbin/"
scp -q systemd/* "$host:/etc/systemd/system/"
ssh "$host" 'chmod 755 /usr/local/sbin/media-state-pull.sh && systemctl daemon-reload && systemctl enable --now media-state-pull.timer'
