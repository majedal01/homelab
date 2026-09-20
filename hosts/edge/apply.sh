#!/usr/bin/env bash
# Push this directory to the edge host and reload the services it feeds.
set -euo pipefail
host="${1:-ubuntu@163.192.213.34}"
cd "$(dirname "$0")"
scp -q Caddyfile iptables/rules.v4 iptables/rules.v6 fail2ban/defaults-debian.conf "$host:/tmp/"
ssh "$host" 'sudo install -m 644 /tmp/Caddyfile /etc/caddy/Caddyfile &&
  sudo install -m 644 /tmp/rules.v4 /tmp/rules.v6 /etc/iptables/ &&
  sudo install -m 644 /tmp/defaults-debian.conf /etc/fail2ban/jail.d/ &&
  sudo systemctl reload caddy && sudo netfilter-persistent reload && sudo systemctl reload fail2ban'
