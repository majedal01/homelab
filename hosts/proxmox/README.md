# proxmox

Single node, i5-12600T, one 512G NVMe. Tailnet name `proxmox`, root over SSH with the
deploy key. Managed by hand; this directory is the record, not an apply target, except the app-state
pull job that `apply.sh` pushes.

- `vm/` is `qm config` for each VM with cloud-init password and ssh keys stripped.
  Recreate a VM from it with `qm create <id>` plus the options listed.
- `modprobe.d/vfio.conf` and `modules` bind the iGPU (8086:4690) to vfio-pci so VM 101
  can take it. The host has no console video as a result.
- `sysctl.d/99-tailscale.conf` turns on forwarding for the Tailscale subnet router.
- `jobs.cfg` is the nightly vzdump job.

## backups

Every VM, midnight, snapshot mode, zstd, to storage `local` (the 94G root filesystem).
Retention keep-daily=7, keep-weekly=4, keep-monthly=2. Pruning runs per VM only after
that VM backs up successfully.

VM 101's 300G disk has `backup=0`. It is 116G of replaceable media and would never fit.
The nightly archive for it holds only the VM definition and EFI vars. Any new VM with a
bulk-data disk needs `backup=0` on that disk at creation time or the job fills the root
filesystem and fails.

VM 101's app state is the part that is not reproducible: Jellyfin users and watch
history, the *arr databases, Seerr, the compose `.env`. About 430M, 200M compressed. The
host pulls it nightly at 03:30 with `media-state-pull.timer`: it runs
`hosts/media/bin/media-state-backup.sh` on the VM over ssh, which pauses the containers,
tars the stack directory minus caches and logs, and resumes them. Archives land in
`/var/lib/vz/dump/media-state-<date>.tar.zst`, last 14 kept. The host's root key sits in
the deploy user's `authorized_keys` on the VM with a forced command, so it can run that
script and nothing else.

Restore: recreate the VM from `vm/101-media.conf`, install docker and the deploy user,
clone the repo, untar the archive into `/home/deploy/stacks/jellyfin`, `docker compose up
-d`, then let Radarr re-download the library.

## iGPU passthrough

VM 101 is q35 + OVMF with `hostpci0: 0000:00:02,pcie=1`. Switching a VM to q35 moves the
disk's PCI path and OVMF keeps its stale boot entry; fix by recreating the efidisk
(`qm set <id> --efidisk0 local-lvm:0,efitype=4m,pre-enrolled-keys=0`). `unused0` on 101
is the old efidisk kept for rollback.
