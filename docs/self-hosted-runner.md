# Budgify Self-Hosted Runner

This repo is wired to deploy from `/srv/budgify` on the homelab LXC.

## Register The Runner

Create the runner account and install the GitHub Actions runner on the LXC:

```bash
sudo useradd --system --create-home --home-dir /opt/actions-runner --shell /usr/sbin/nologin actions-runner
sudo usermod -aG docker actions-runner
sudo mkdir -p /opt/actions-runner/budgify

cd /opt/actions-runner/budgify
curl -fsSL -o actions-runner-linux-x64.tar.gz \
  https://github.com/actions/runner/releases/download/v2.335.1/actions-runner-linux-x64-2.335.1.tar.gz
tar xzf actions-runner-linux-x64.tar.gz
```

Register the runner with labels:

```bash
token=$(gh api -X POST repos/alisaleemh/budgify/actions/runners/registration-token --jq .token)
sudo -u actions-runner ./config.sh --unattended \
  --url https://github.com/alisaleemh/budgify \
  --token "$token" \
  --name homelab-budgify \
  --labels homelab,docker-compose,budgify \
  --work _work
```

Install the systemd unit once on the LXC:

```bash
sudo tee /etc/systemd/system/actions-runner@.service >/dev/null <<'UNIT'
[Unit]
Description=GitHub Actions Runner (%i)
After=network-online.target docker.service
Wants=network-online.target docker.service

[Service]
Type=simple
User=actions-runner
Group=actions-runner
WorkingDirectory=/opt/actions-runner/%i
ExecStart=/opt/actions-runner/%i/run.sh
Restart=always
RestartSec=5
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now actions-runner@budgify
```

## Start, Stop, Status

```bash
sudo systemctl start actions-runner@budgify
sudo systemctl stop actions-runner@budgify
sudo systemctl status actions-runner@budgify
```

## Test The Workflow

Run the workflow manually with `workflow_dispatch` and `mode=test`.
That job only runs:

```bash
whoami
hostname
docker version
docker compose version
docker compose config
```

To enable real push-to-main deploys, create the local gate file on the LXC:

```bash
touch /srv/budgify/.deploy-enabled
```

Remove that file to pause automatic deploys:

```bash
rm -f /srv/budgify/.deploy-enabled
```

## Rollback

If a deployment fails, stop the service stack and roll back the repo checkout manually:

```bash
cd /srv/budgify
docker compose down
git fetch origin main
git reset --hard origin/main~1
./deploy.sh
```

If you only need to recover the running containers without changing code, rerun:

```bash
cd /srv/budgify
./deploy.sh
```
