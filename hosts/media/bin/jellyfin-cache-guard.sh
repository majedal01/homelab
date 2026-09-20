#!/bin/bash
# Disk guard for the media VM. Keeps the disk from filling and taking Jellyfin (and the
# VPN sidecar) down, as happened 2026-06-14 (runaway transcode cache) and 2026-07-23
# (62G of abandoned usenet incompletes). Runs every 20 min via jellyfin-cache-guard.timer.
STACK=/home/deploy/stacks/jellyfin
CACHE="$STACK/cache/transcodes"
INCOMPLETE=/data/usenet/incomplete
MIN_FREE_GB=20
WARN_PCT=85
ORPHAN_DAYS=2

free_gb() { df -BG --output=avail / | tail -1 | tr -dc '0-9'; }
used_pct() { df --output=pcent / | tail -1 | tr -dc '0-9'; }

free=$(free_gb); pct=$(used_pct)
[ -z "$free" ] && exit 0

# Warn early, well before the cliff.
if [ -n "$pct" ] && [ "$pct" -ge "$WARN_PCT" ]; then
  logger -t disk-guard "WARNING: / at ${pct}% used (${free}G free)"
fi

# Reclaim regenerable space when low.
if [ "$free" -lt "$MIN_FREE_GB" ]; then
  rm -rf "$CACHE"/* 2>/dev/null
  docker image prune -f >/dev/null 2>&1
  logger -t disk-guard "low disk: ${free}G free, cleared transcode cache -> $(free_gb)G free"
fi

# Sweep abandoned usenet jobs: older than ORPHAN_DAYS and absent from SABnzbd's queue.
# If SABnzbd cannot be queried the sweep is skipped, so an active job is never removed.
key=$(grep -oP '^api_key\s*=\s*\K\S+' "$STACK/sabnzbd/sabnzbd.ini" 2>/dev/null | head -1)
[ -z "$key" ] && exit 0
active=$(curl -sf -m 15 "http://127.0.0.1:8085/api?mode=queue&output=json&apikey=$key" \
  | python3 -c 'import sys,json
for s in json.load(sys.stdin)["queue"].get("slots",[]): print(s.get("filename",""))' 2>/dev/null) || exit 0

find "$INCOMPLETE" -mindepth 1 -maxdepth 1 -type d -mtime +$ORPHAN_DAYS 2>/dev/null | while read -r d; do
  name=$(basename "$d")
  grep -Fxq "$name" <<<"$active" && continue
  size=$(du -sh "$d" 2>/dev/null | cut -f1)
  rm -rf "$d" && logger -t disk-guard "removed abandoned incomplete: $name ($size)"
done
