# edge

Oracle Cloud Always Free ARM VM, Ubuntu 24.04, tailnet `oracle-edge`, reserved public IP
163.192.213.34. Home is behind an ISP gateway with no bridge mode, so public ingress
terminates here and Caddy proxies over Tailscale to the media VM. Certs are Let's Encrypt
HTTP-01. DNS A records for the two hostnames point at this IP, not proxied.

- `Caddyfile` at `/etc/caddy/Caddyfile`, Caddy from apt.
- `iptables/` is the netfilter-persistent ruleset: 22, 80, 443 in, plus Oracle's
  instance-services chain. The OCI security list must allow the same ports.
- `fail2ban/` bans sshd brute force; thousands of bans a month is normal here.

`apply.sh` pushes all three and reloads. Tailscale key expiry is still enabled for this
node; disable it in the admin console or it drops off the tailnet every 90 days.
