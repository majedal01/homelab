# infra

Shared, cross-app infrastructure. Anything specific to one app (its Docker Compose
stacks, Dockerfiles, env examples) lives with that app under
[`apps/<app>/deploy/`](../apps/), not here.

Reserved for platform-wide concerns such as the Cloudflare Tunnel config. The
reusable deploy workflow lives in [`.github/workflows/deploy.yml`](../.github/workflows/deploy.yml).

See [`../docs/CONVENTIONS.md`](../docs/CONVENTIONS.md) for naming and namespacing
rules, and [`../docs/deployment.md`](../docs/deployment.md) for the CD flow.