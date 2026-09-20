#!/usr/bin/env bash
# Pull the media VM's app state over ssh into local storage and keep the last 14.
# The host's key is restricted on the VM to the backup script by a forced command,
# so this is the only thing it can run there. Pull rather than push: the hypervisor
# already controls the VM, so no credential has to travel the other way.
set -euo pipefail
dest=/var/lib/vz/dump
keep=14
vm=deploy@100.84.50.127
out="$dest/media-state-$(date +%F).tar.zst"
tmp="$out.part"
ssh -o BatchMode=yes -o ConnectTimeout=20 "$vm" media-state-backup > "$tmp"
zstd -t -q "$tmp"
[ "$(stat -c %s "$tmp")" -gt 10000000 ] || { echo "archive suspiciously small, keeping .part" >&2; exit 1; }
mv "$tmp" "$out"
ls -1t "$dest"/media-state-*.tar.zst | tail -n +$((keep + 1)) | xargs -r rm -f
echo "wrote $out ($(du -h "$out" | cut -f1))"
