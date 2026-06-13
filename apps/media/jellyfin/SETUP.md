# Media VM setup and first deploy

Provision a dedicated media VM on the Proxmox host, then bring up the Jellyfin MVP. The
media VM is separate from the app VM that runs ynabInsights. One-time setup; afterwards a
a deploy is `docker compose pull && up -d` in the stack folder.

## 1. Create the VM (Proxmox web UI, https://100.66.36.86:8006)

1. Upload an **Ubuntu Server 24.04 LTS** ISO under `local > ISO Images` (or use a
   cloud-init template).
2. **Create VM**:
   - OS: the Ubuntu ISO.
   - System: default (SeaBIOS), QEMU guest agent on.
   - Disk: ~200 GB on the available storage (the M90q's 512 GB NVMe is shared with Proxmox
     and the app VM, so check free space first; grow or add a disk later for the library).
   - CPU: 4 cores, **Type: `host`** (lets QuickSync iGPU passthrough work in Phase 3).
   - Memory: 6 GB (4 GB floor).
   - Network: bridge `vmbr0`.
3. Start the VM, install Ubuntu, create your admin user, enable OpenSSH during install.

## 2. Base setup (SSH into the new VM)

```bash
sudo apt update && sudo apt -y upgrade

# Docker + compose plugin
curl -fsSL https://get.docker.com | sudo sh

# deploy user (mirrors the app VM), passwordless sudo, in the docker group
sudo useradd -m -s /bin/bash deploy
echo 'deploy ALL=(ALL) NOPASSWD:ALL' | sudo tee /etc/sudoers.d/deploy
sudo usermod -aG docker deploy
sudo -u deploy mkdir -p /home/deploy/.ssh
# authorize your homelab_deploy public key:
sudo -u deploy tee /home/deploy/.ssh/authorized_keys < /dev/stdin   # paste the .pub, Ctrl-D
sudo -u deploy chmod 600 /home/deploy/.ssh/authorized_keys

# Tailscale (join the tailnet; note the 100.x address it prints)
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
tailscale ip -4

# Unified data root + stack folder (single filesystem -> hardlinks work in Phase 2)
sudo mkdir -p /data/media/movies
sudo chown -R deploy:deploy /data
sudo -u deploy mkdir -p /home/deploy/stacks/jellyfin
```

Add a `Host 100-media` block to your laptop `~/.ssh/config` pinning the tailnet IP (MagicDNS
is flaky), mirroring the existing `100-ubuntu` block.

## 3. Deploy Jellyfin (MVP)

From your laptop, copy the appliance files to the stack folder (or `git clone` the repo on
the VM and copy from `apps/media/jellyfin/deploy/`):

```bash
scp -i ~/.ssh/homelab_deploy \
  apps/media/jellyfin/deploy/docker-compose.yml \
  apps/media/jellyfin/deploy/.env.example \
  deploy@<media-tailnet-ip>:/home/deploy/stacks/jellyfin/
```

On the media VM:

```bash
cd /home/deploy/stacks/jellyfin
cp .env.example .env
id        # set PUID/PGID in .env to this uid:gid; set TZ
# Drop one film at /data/media/movies/Movie Name (Year)/Movie Name (Year).mkv
docker compose up -d
docker compose ps
```

## 4. First run

1. Browse to `http://<media-tailnet-ip>:8096` (you are on the tailnet; no SSH forward
   needed). Run the setup wizard and create the admin user.
2. Add a **Movies** library pointing at `/data/media/movies`; let it scrape metadata.
3. On the Apple TV / iPhone, install **Infuse**, add a **Jellyfin** source at the same
   tailnet address, sign in, and play the movie.

**Done when** the movie plays in Infuse and the Jellyfin dashboard (Dashboard > Activity)
shows **Direct Play**, not Transcode.

Next: the *arr automation pipeline and the public-HTTPS + transcoding work in
[DESIGN.md](DESIGN.md).
